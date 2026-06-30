"""Launch the local self-audit web app."""

from __future__ import annotations

import argparse
import threading
import webbrowser

import uvicorn


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local biomedical self-audit web app.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser window automatically.")
    args = parser.parse_args()

    url = f"http://{args.host}:{args.port}"
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run("webapp.backend.app:create_app", factory=True, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
