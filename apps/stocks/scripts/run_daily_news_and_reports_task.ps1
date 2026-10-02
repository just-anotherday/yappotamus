param(
    [string[]]$DailyArguments = @(),
    [ValidateRange(1,65535)][int]$BackendPort = 8000,
    [ValidateRange(1,600)][int]$BackendStartupTimeoutSeconds = 90,
    [ValidateRange(1,120)][int]$BackendShutdownTimeoutSeconds = 20
)

$ErrorActionPreference = 'Stop'
$stocksRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$repoRoot = [IO.Path]::GetFullPath((Join-Path $stocksRoot '..\..'))
$python = Join-Path $stocksRoot '.venv\Scripts\python.exe'
$dailyScript = Join-Path $stocksRoot 'scripts\run_daily_news_and_reports.py'
$backendScript = Join-Path $stocksRoot 'scripts\run_task_backend.py'
$logDirectory = Join-Path $stocksRoot 'logs\daily-task'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$runId = '{0}-{1}' -f (Get-Date -Format 'yyyyMMdd-HHmmss-fff'), $PID
$runnerLog = Join-Path $logDirectory "$runId.runner.log"
$stdoutLog = Join-Path $logDirectory "$runId.stdout.log"
$stderrLog = Join-Path $logDirectory "$runId.stderr.log"
$stopFile = Join-Path $logDirectory "$runId.backend.stop"
$pidFile = Join-Path $logDirectory "$runId.backend.pid"
$healthUrl = "http://127.0.0.1:$BackendPort/health/ready"
function Write-Runner([string]$Message) {
    "timestamp=$((Get-Date).ToString('o')) $Message" | Add-Content -LiteralPath $runnerLog
}
function Test-BackendReady {
    try {
        $response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 3
        $body = $response.Content | ConvertFrom-Json
        return ($response.StatusCode -eq 200 -and $body.status -eq 'ready' -and $body.database -eq 'reachable')
    } catch { return $false }
}
Write-Runner 'launcher_started'
try {
    $lockStream = [IO.File]::Open((Join-Path $logDirectory 'daily-task.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
} catch [IO.IOException] {
    Write-Runner 'outcome=duplicate_run_skipped launcher_exit_code=75'
    exit 75
}
$exitCode = 70 # launcher/infrastructure failure
$pipelineExitCode = $null
$backend = $null
$serverProcess = $null
$preexisting = $false
$cleanupFailed = $false
try {
    foreach ($path in @($python, $dailyScript, $backendScript)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw 'Required launcher dependency missing' }
    }
    $preexisting = Test-BackendReady
    Write-Runner "backend_preexisting=$($preexisting.ToString().ToLower()) health_url=$healthUrl"
    if (-not $preexisting) {
        $exitCode = 71 # startup/readiness failure; pipeline never started
        # An occupied, unhealthy port is not ours. Do not start or kill its process.
        $listener = Get-NetTCPConnection -State Listen -LocalPort $BackendPort -ErrorAction SilentlyContinue
        if ($listener) { Write-Runner 'backend_startup_failure=unhealthy_port_occupied'; throw 'Backend port is occupied but readiness failed' }
        $backendArgs = @('"' + $backendScript + '"', '--port', "$BackendPort", '--stop-file', '"' + $stopFile + '"', '--pid-file', '"' + $pidFile + '"')
        Write-Runner "backend_command=`"$python`" $($backendArgs -join ' ')"
        $backend = Start-Process -FilePath $python -ArgumentList $backendArgs -WorkingDirectory $stocksRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDirectory "$runId.backend.stdout.log") -RedirectStandardError (Join-Path $logDirectory "$runId.backend.stderr.log")
        Write-Runner "backend_started_by_launcher=true backend_start_pid=$($backend.Id)"
        $timer = [Diagnostics.Stopwatch]::StartNew()
        $ready = $false
        $attempt = 0
        while ($timer.Elapsed.TotalSeconds -lt $BackendStartupTimeoutSeconds) {
            $attempt++
            $backend.Refresh()
            if ($backend.HasExited) { Write-Runner 'backend_startup_failure=process_exited'; throw 'Owned backend exited before readiness' }
            $ready = Test-BackendReady
            Write-Runner "health_attempt=$attempt ready=$($ready.ToString().ToLower())"
            if ($ready) { break }
            Start-Sleep -Milliseconds 500
        }
        if (-not $ready) { Write-Runner 'backend_startup_failure=readiness_timeout'; throw 'Backend readiness timeout' }
        # Windows venv python may be a redirector. Capture the actual server too.
        $serverPid = [int](Get-Content -LiteralPath $pidFile -Raw)
        $serverProcess = Get-Process -Id $serverPid -ErrorAction Stop
        $serverInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$serverPid"
        if ($serverPid -ne $backend.Id -and $serverInfo.ParentProcessId -ne $backend.Id) { throw 'Backend PID ownership mismatch' }
        $ownedListener = Get-NetTCPConnection -State Listen -LocalPort $BackendPort -ErrorAction Stop | Where-Object OwningProcess -eq $serverPid
        if (-not $ownedListener) { throw 'Readiness listener does not belong to owned backend' }
        Write-Runner "backend_ready backend_server_pid=$serverPid"
    } else {
        Write-Runner 'backend_started_by_launcher=false backend_ready'
    }
    $exitCode = 70
    Write-Runner 'pipeline_started'
    $process = Start-Process -FilePath $python -ArgumentList (@('"' + $dailyScript + '"') + $DailyArguments) -WorkingDirectory $repoRoot -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog -WindowStyle Hidden -Wait -PassThru
    $pipelineExitCode = $process.ExitCode
    $exitCode = $pipelineExitCode
    Write-Runner "python_exit_code=$pipelineExitCode"
} catch {
    # Exception messages can contain connection credentials; record only type/stage.
    Write-Runner "launcher_exception_type=$($_.Exception.GetType().Name) failure_status=$exitCode"
} finally {
    try {
        if ($null -ne $backend) {
            Write-Runner "backend_shutdown_started backend_start_pid=$($backend.Id)"
            [IO.File]::WriteAllText($stopFile, 'stop')
            if (-not $backend.WaitForExit($BackendShutdownTimeoutSeconds * 1000)) {
                Write-Runner 'backend_shutdown_forced=true'
                # Only the process tree retained from Start-Process is eligible.
                & "$env:SystemRoot\System32\taskkill.exe" /PID $backend.Id /T /F | Out-Null
                if (-not $backend.WaitForExit(5000)) { throw 'Owned backend did not exit' }
            }
            if ($null -ne $serverProcess -and -not $serverProcess.WaitForExit(5000)) { throw 'Owned server remains alive' }
            Write-Runner 'backend_shutdown_result=stopped'
        } elseif ($preexisting) {
            Write-Runner 'backend_shutdown_skipped_preexisting'
        }
    } catch {
        $cleanupFailed = $true
        Write-Runner "backend_shutdown_result=failed exception_type=$($_.Exception.GetType().Name)"
        # Retain nonzero pipeline/startup failures. Cleanup after success uses 72.
        if ($exitCode -eq 0) { $exitCode = 72 }
    } finally {
        Write-Runner "pipeline_exit_code=$pipelineExitCode cleanup_failed=$($cleanupFailed.ToString().ToLower()) launcher_exit_code=$exitCode"
        Write-Runner 'launcher_finished'
        $lockStream.Dispose()
    }
}
exit $exitCode
