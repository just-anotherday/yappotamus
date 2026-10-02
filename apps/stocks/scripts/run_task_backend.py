"""Single-process Stocks server with launcher-owned, graceful Windows shutdown.

Uses the same app and Windows loop factory as run.py, without its dev reloader.
The unique stop file is private to one launcher run; no HTTP shutdown API exists.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import threading


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--stop-file", type=Path, required=True)
    parser.add_argument("--pid-file", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    sys.path.insert(0, str(root))
    # Must precede app import. Never starts a second ingestion/report scheduler.
    os.environ["STOCKS_TASK_MANAGED_BACKEND"] = "1"
    import run  # loads the existing .env without overriding inherited values
    import uvicorn

    server = uvicorn.Server(uvicorn.Config(
        "backend.main:app", host="127.0.0.1", port=args.port,
        loop="run:new_selector_event_loop" if sys.platform == "win32" else "auto",
        reload=False, log_level="info", timeout_graceful_shutdown=10,
    ))
    args.pid_file.write_text(str(os.getpid()), encoding="ascii")
    print(f"backend_server_pid={os.getpid()}", flush=True)
    finished = threading.Event()

    def watch_stop() -> None:
        while not finished.wait(0.2):
            if args.stop_file.exists():
                server.should_exit = True
                return

    threading.Thread(target=watch_stop, daemon=True).start()
    try:
        server.run()
        return 0 if server.started else 1
    finally:
        finished.set()


if __name__ == "__main__":
    raise SystemExit(main())
