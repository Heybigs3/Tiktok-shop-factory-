"""Entry point for the dashboard: python -m src.dashboard

Starts the FastAPI server on port 8420 and auto-opens the browser.
"""

import threading
import time
import webbrowser

import uvicorn

HOST = "127.0.0.1"
PORT = 8420
URL = f"http://{HOST}:{PORT}"


def open_browser():
    """Wait briefly for the server to start, then open the browser."""
    time.sleep(1.2)
    webbrowser.open(URL)


def main():
    print(f"\n  TikTok Factory — Mission Control")
    print(f"  Starting at {URL}")
    print(f"  Press Ctrl+C to stop\n")

    # Auto-open browser in a background thread
    threading.Thread(target=open_browser, daemon=True).start()

    uvicorn.run(
        "src.dashboard.app:app",
        host=HOST,
        port=PORT,
        reload=False,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
