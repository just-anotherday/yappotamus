'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import IntelligenceCard from '@/components/intelligence/IntelligenceCard';
import MarketReportCard from '@/components/intelligence/MarketReportCard';
import type { CachedCompanyReport } from '@/types/stock';
import {
  fetchCompanyReportsBatch,
  fetchCompanyReport,
  triggerCompanyReportRegeneration,
  triggerAllCompanyReports,
  fetchNewsTickers,
  fetchOllamaConfig,
} from '@/lib/api';
import { getWatchlistConfig } from '@/lib/api';
import type { OllamaConfig } from '@/lib/api';

export default function IntelligenceDashboard() {
  const [reports, setReports] = useState<CachedCompanyReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tickers, setTickers] = useState<string[]>([]);
  const [regenerating, setRegenerating] = useState<string | null>(null);
  const [regeneratingAll, setRegeneratingAll] = useState(false);
  const [ollamaConfig, setOllamaConfig] = useState<OllamaConfig | null>(null);
  const [selectedModel, setSelectedModel] = useState<string>('');
  // Track which tickers are actively being processed by the AI worker
  const [processing, setProcessing] = useState<Set<string>>(new Set());
  // Track queue status per ticker: 'queued' | 'processing' | null
  const [queueStatus, setQueueStatus] = useState<Record<string, string>>({});
  // Track how many have completed during a "Regenerate All" run
  const [completedCount, setCompletedCount] = useState(0);
  // Completion notification
  const [completionMsg, setCompletionMsg] = useState<string | null>(null);
  const pollRefs = useRef<Map<string, ReturnType<typeof setInterval>>>(new Map());

  const loadReports = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      let tickerList: string[];

      // Try default tickers from config first, fall back to DB watchlist
      const config = await getWatchlistConfig();
      if (config.default_tickers && config.default_tickers.length > 0) {
        tickerList = config.default_tickers;
      } else {
        try {
          tickerList = await fetchNewsTickers();
        } catch {
          tickerList = [];
        }
      }

      setTickers(tickerList);

      if (tickerList.length === 0) {
        setError('No tickers configured. Add tickers to your watchlist first.');
        setLoading(false);
        return;
      }

      const results = await fetchCompanyReportsBatch(tickerList);
      setReports(results);
      if (results.length === 0) {
        setError('No cached intelligence reports available. Reports are generated asynchronously when new news arrives.');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load intelligence reports');
    } finally {
      setLoading(false);
    }
  }, []);

  // Stop all polling intervals on unmount
  useEffect(() => {
    return () => {
      pollRefs.current.forEach(interval => clearInterval(interval));
      pollRefs.current.clear();
    };
  }, []);

  useEffect(() => {
    loadReports();

    // Fetch Ollama config for model selector
    fetchOllamaConfig()
      .then(cfg => {
        setOllamaConfig(cfg);
        if (cfg.available_models && cfg.available_models.length > 0) {
          // Try localStorage first, fall back to server default
          const saved = typeof window !== 'undefined' ? localStorage.getItem('selectedAiModel') : null;
          if (saved && cfg.available_models.find(m => m.name === saved)) {
            setSelectedModel(saved);
          } else {
            setSelectedModel(cfg.default_model || cfg.available_models[0].name);
          }
        }
      })
      .catch(err => console.warn('Failed to fetch Ollama config:', err));
  }, [loadReports]);

  // Persist selected model to localStorage whenever it changes
  useEffect(() => {
    if (selectedModel && ollamaConfig?.available_models?.find(m => m.name === selectedModel)) {
      localStorage.setItem('selectedAiModel', selectedModel);
    }
  }, [selectedModel, ollamaConfig]);

  /** Start polling for a single ticker report until its last_updated changes */
  const startPollingForTicker = (ticker: string, baselineTimestamp: string | null, isBatchRun = false) => {
    // Clear any existing poll for this ticker
    const existing = pollRefs.current.get(ticker);
    if (existing) clearInterval(existing);

    const interval = setInterval(async () => {
      try {
        const updated = await fetchCompanyReport(ticker.toUpperCase());
        // Check if the report was actually updated
        if (baselineTimestamp && updated.last_updated !== baselineTimestamp) {
          clearInterval(interval);
          pollRefs.current.delete(ticker);
          setProcessing(prev => {
            const next = new Set(prev);
            next.delete(ticker);
            return next;
          });
          setQueueStatus(prev => ({ ...prev, [ticker]: '' }));
          // Increment completed count for batch runs
          if (isBatchRun) {
            setCompletedCount(prev => prev + 1);
          }
          // Update this single report in the list
          setReports(prev => prev.map(r => r.ticker === ticker ? updated : r));
          setRegenerating(null);
        }
      } catch {
        // Report doesn't exist yet or error - keep polling
      }
    }, 3000); // Poll every 3 seconds

    pollRefs.current.set(ticker, interval);

    // Auto-stop after 90 seconds timeout
    setTimeout(() => {
      clearInterval(interval);
      pollRefs.current.delete(ticker);
      setProcessing(prev => {
        const next = new Set(prev);
        next.delete(ticker);
        return next;
      });
      setQueueStatus(prev => ({ ...prev, [ticker]: '' }));
      if (isBatchRun) {
        setCompletedCount(prev => prev + 1);
      }
      setRegenerating(null);
    }, 90000);
  };

  const handleRegenerate = async (ticker: string) => {
    setRegenerating(ticker);
    setProcessing(prev => new Set(prev).add(ticker));
    setQueueStatus(prev => ({ ...prev, [ticker]: 'queued' }));

    // Get current baseline timestamp before triggering
    let baselineTimestamp: string | null = null;
    try {
      const current = await fetchCompanyReport(ticker.toUpperCase());
      baselineTimestamp = current.last_updated;
    } catch {
      // No existing report yet - baseline is null, poll until one appears
    }

    try {
      await triggerCompanyReportRegeneration(ticker, selectedModel || undefined);
      setQueueStatus(prev => ({ ...prev, [ticker]: 'processing' }));
      startPollingForTicker(ticker, baselineTimestamp);
    } catch (err) {
      console.error(`Failed to regenerate ${ticker}:`, err);
      setProcessing(prev => {
        const next = new Set(prev);
        next.delete(ticker);
        return next;
      });
      setQueueStatus(prev => ({ ...prev, [ticker]: '' }));
      setRegenerating(null);
    }
  };

  const handleRegenerateAll = async () => {
    if (regeneratingAll) return;
    setRegeneratingAll(true);
    setCompletedCount(0);
    setCompletionMsg(null);

    // Get baseline timestamps for all tickers before triggering
    const baselines = new Map<string, string | null>();
    for (const t of tickers) {
      try {
        const current = await fetchCompanyReport(t.toUpperCase());
        baselines.set(t, current.last_updated);
      } catch {
        baselines.set(t, null);
      }
      setProcessing(prev => new Set(prev).add(t));
      setQueueStatus(prev => ({ ...prev, [t]: 'queued' }));
    }

    try {
      await triggerAllCompanyReports(tickers, selectedModel || undefined);

      // Mark all as processing
      const statusUpdate: Record<string, string> = {};
      tickers.forEach(t => { statusUpdate[t] = 'processing'; });
      setQueueStatus(prev => ({ ...prev, ...statusUpdate }));

      // Start polling for each ticker (batch mode)
      for (const t of tickers) {
        startPollingForTicker(t, baselines.get(t) || null, true);
      }

      // Listen for all completions
      const total = tickers.length;
      const checkComplete = setInterval(() => {
        setCompletedCount(prev => {
          if (prev >= total && total > 0) {
            clearInterval(checkComplete);
            setRegeneratingAll(false);
            setCompletionMsg(`✅ Analysis complete for ${prev} ticker${prev > 1 ? 's' : ''}`);
            setTimeout(() => setCompletionMsg(null), 8000);
            // Refresh the full report list
            loadReports();
            return prev;
          }
          return prev;
        });
      }, 1000);

      // Hard timeout after 15 minutes
      setTimeout(() => {
        clearInterval(checkComplete);
        setRegeneratingAll(false);
        setCompletionMsg(null);
        loadReports();
      }, 900000);
    } catch (err) {
      console.error('Failed to regenerate all:', err);
      setRegeneratingAll(false);
    }
  };

  // Progress text for regenerate buttons based on queue status
  function getProgressLabel(ticker: string): string {
    if (regenerating === ticker) return '📤 Queued...';
    const status = queueStatus[ticker];
    if (status === 'queued') return '📤 Queued...';
    if (status === 'processing') return `⏳ Analyzing with ${selectedModel || 'AI'}...`;
    return '🔄 Regenerate';
  }

  function getStatusBadge(ticker: string): React.ReactNode {
    const status = queueStatus[ticker];
    if (status === 'queued') return <span style={{display:'inline-block',padding:'2px 8px',borderRadius:4,background:'#fff3e0',color:'#e65100',fontSize:11,fontWeight:700}}>📤 Queued</span>;
    if (status === 'processing') return <span style={{display:'inline-block',padding:'2px 8px',borderRadius:4,background:'#e3f2fd',color:'#1565c0',fontSize:11,fontWeight:700}}>⏳ Processing</span>;
    return null;
  }

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: '40px 20px' }}>
      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <h1 style={{ fontSize: 28, fontWeight: 800, margin: '0 0 8px', color: 'var(--text-primary)' }}>
          🧠 AI Intelligence Dashboard
        </h1>
        <p style={{ color: 'var(--text-secondary)', margin: 0, fontSize: 14 }}>
          Cached AI-generated analysis for your watched tickers. Click any card to see the full report.
        </p>
      </div>

      {/* Stats Bar + Model Toggle */}
      <div style={{ display: 'flex', gap: 24, alignItems: 'center', marginBottom: 16, fontSize: 13, color: 'var(--text-muted)' }}>
        {loading ? (
          <span>📊 Loading tickers...</span>
        ) : (
          <span>📊 {reports.length} / {tickers.length} tickers analyzed</span>
        )}
        {processing.size > 0 && <span>⏳ Processing {processing.size}...</span>}
        {loading && <span>⏳ Refreshing...</span>}

        {/* Model Toggle Bar */}
        {ollamaConfig && ollamaConfig.available_models && ollamaConfig.available_models.length > 0 && (
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 4 }}>
            <label style={{ fontSize: 13, color: 'var(--text-muted)', marginRight: 4 }}>AI Model:</label>
            {ollamaConfig.available_models.map(m => (
              <button
                key={m.name}
                onClick={() => setSelectedModel(m.name)}
                style={{
                  padding: '4px 12px',
                  borderRadius: 16,
                  border: selectedModel === m.name ? '2px solid #ff9800' : '1px solid var(--card-border)',
                  background: selectedModel === m.name ? '#fff3e0' : 'var(--card-bg)',
                  color: selectedModel === m.name ? '#e65100' : 'var(--text-secondary)',
                  fontSize: 12,
                  fontWeight: selectedModel === m.name ? 700 : 400,
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                }}
              >
                {m.name}
              </button>
            ))}
            <span style={{
              width: 8, height: 8, borderRadius: '50%', marginLeft: 4,
              background: ollamaConfig.connected ? '#4caf50' : '#f44336',
              display: 'inline-block',
            }} title={ollamaConfig.connected ? 'Ollama connected' : 'Ollama disconnected'} />
          </div>
        )}
      </div>

      {/* Current Model Display */}
      {selectedModel && (
        <div style={{ marginBottom: 24, fontSize: 12, color: 'var(--text-muted)' }}>
          🎯 Selected model for next analysis: <strong>{selectedModel}</strong>
        </div>
      )}

      {/* Completion Notification */}
      {completionMsg && (
        <div style={{
          padding: '10px 20px',
          marginBottom: 24,
          background: '#e8f5e9',
          borderRadius: 8,
          border: '1px solid #a5d6a7',
          color: '#2e7d32',
          fontWeight: 600,
          fontSize: 14,
        }}>
          {completionMsg}
        </div>
      )}

      {/* Regenerate All Button */}
      <div style={{ marginBottom: 24 }}>
        <button
          onClick={handleRegenerateAll}
          disabled={regeneratingAll || loading || tickers.length === 0}
          style={{
            padding: '10px 24px',
            background: regeneratingAll ? '#9e9e9e' : '#ff9800',
            color: '#fff',
            border: 'none',
            borderRadius: 8,
            fontSize: 14,
            fontWeight: 700,
            cursor: regeneratingAll || loading ? 'not-allowed' : 'pointer',
          }}
        >
          {regeneratingAll
            ? `⏳ Regenerating... (${completedCount}/${tickers.length} done)`
            : `🔄 Regenerate All (${tickers.length} tickers)`}
        </button>
        {selectedModel && (
          <span style={{ fontSize: 12, color: 'var(--text-muted)', marginLeft: 12 }}>
            Will use: {selectedModel}
          </span>
        )}
      </div>

      {/* Market Report Card (Daily Summary) */}
      <MarketReportCard />

      {/* Error State */}
      {error && !loading && (
        <div style={{
          padding: 20,
          background: 'var(--section-bg)',
          borderRadius: 8,
          marginBottom: 24,
          border: '1px solid var(--card-border)',
          color: 'var(--text-primary)',
        }}>
          <p style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>{error}</p>
          <button
            onClick={loadReports}
            style={{ marginTop: 12, padding: '8px 16px', background: '#ff9800', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 600 }}
          >
            Retry
          </button>
        </div>
      )}

      {/* Loading State */}
      {loading && reports.length === 0 && (
        <div style={{ textAlign: 'center', padding: 80, color: 'var(--text-muted)' }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>🔄</div>
          <p>Loading intelligence reports...</p>
        </div>
      )}

      {/* Grid of Intelligence Cards */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
        gap: 20,
      }}>
         {reports.map(report => (
           <IntelligenceCard
             key={report.ticker}
             report={report}
            onRegenerate={() => handleRegenerate(report.ticker)}
            isProcessing={processing.has(report.ticker) || regenerating === report.ticker}
            queueStatusText={getProgressLabel(report.ticker)}
          />
        ))}
      </div>

      {/* Missing Reports Section */}
      {reports.length < tickers.length && (
        <div style={{ marginTop: 40, padding: 24, background: 'var(--card-bg)', borderRadius: 12 }}>
          <h3 style={{ margin: '0 0 12px', fontSize: 16, color: 'var(--text-primary)' }}>Missing Reports</h3>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: '0 0 16px' }}>
            These tickers don't have cached reports yet. Queue them for AI analysis:
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {tickers
              .filter(t => !reports.find(r => r.ticker === t))
              .map(ticker => (
                <button
                  key={ticker}
                  onClick={() => handleRegenerate(ticker)}
                  disabled={processing.has(ticker) || regenerating === ticker}
                  style={{
                    padding: '8px 16px',
                    background: processing.has(ticker) ? (queueStatus[ticker] === 'processing' ? '#e3f2fd' : '#fff3e0') : (regenerating === ticker ? '#9e9e9e' : '#2196f3'),
                    color: processing.has(ticker) ? (queueStatus[ticker] === 'processing' ? '#1565c0' : '#e65100') : '#fff',
                    border: 'none',
                    borderRadius: 6,
                    fontSize: 13,
                    fontWeight: 600,
                    cursor: processing.has(ticker) || regenerating === ticker ? 'not-allowed' : 'pointer',
                  }}
                >
                  {processing.has(ticker)
                    ? (queueStatus[ticker] === 'processing' ? `⏳ ${ticker}` : `📤 ${ticker}`)
                    : (regenerating === ticker ? `📤 ${ticker}` : `+ ${ticker}`)}
                </button>
              ))
            }
          </div>
        </div>
      )}
    </div>
  );
}
