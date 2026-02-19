"""
LiveView Server — Real-time visual rendering of the browser state.

Runs a lightweight Flask server on localhost:18900 that auto-refreshes
screenshots from the browser, providing a visual window into what the
agent is doing.
"""

import io
import time
import threading
from typing import Optional


# The HTML template — auto-refreshes every 2 seconds
_LIVE_VIEW_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Agent-S LiveView</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: #0a0a0f;
            font-family: 'Segoe UI', system-ui, sans-serif;
            color: #e0e0e0;
            display: flex;
            flex-direction: column;
            align-items: center;
            min-height: 100vh;
        }
        header {
            width: 100%;
            padding: 12px 24px;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            border-bottom: 1px solid #2a2a4a;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        header h1 {
            font-size: 16px;
            font-weight: 600;
            background: linear-gradient(90deg, #00d2ff, #7b2ff7);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .status {
            font-size: 12px;
            color: #888;
        }
        .status.live { color: #00ff88; }
        .status.live::before { content: '● '; }
        .container {
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 16px;
            width: 100%;
        }
        #screenshot {
            max-width: 100%;
            max-height: calc(100vh - 80px);
            border-radius: 8px;
            box-shadow: 0 4px 24px rgba(0,0,0,0.5);
            transition: opacity 0.3s;
        }
        #screenshot.loading { opacity: 0.5; }
        .error-msg {
            color: #ff6b6b;
            font-size: 14px;
            text-align: center;
            padding: 40px;
        }
    </style>
</head>
<body>
    <header>
        <h1>🔭 Agent-S LiveView</h1>
        <span id="status" class="status">Connecting...</span>
    </header>
    <div class="container">
        <img id="screenshot" src="/frame" alt="Browser View"
             onerror="this.style.display='none'; document.getElementById('error').style.display='block';"
             onload="this.style.display='block'; document.getElementById('error').style.display='none';">
        <div id="error" class="error-msg" style="display:none;">
            No browser screenshot available.<br>
            Make sure the browser is running.
        </div>
    </div>
    <script>
        const img = document.getElementById('screenshot');
        const status = document.getElementById('status');
        let refreshInterval = 2000;
        let errorCount = 0;

        function refresh() {
            const newImg = new Image();
            const ts = Date.now();
            newImg.onload = function() {
                img.src = newImg.src;
                status.textContent = 'Live — ' + new Date().toLocaleTimeString();
                status.className = 'status live';
                errorCount = 0;
            };
            newImg.onerror = function() {
                errorCount++;
                if (errorCount > 3) {
                    status.textContent = 'Disconnected';
                    status.className = 'status';
                }
            };
            newImg.src = '/frame?t=' + ts;
        }

        setInterval(refresh, refreshInterval);
        refresh();
    </script>
</body>
</html>"""


class LiveViewServer:
    """
    Lightweight HTTP server for real-time browser screenshot display.

    Usage:
        from nexus.browser.browser_client import BrowserClient
        from nexus.browser.live_view import LiveViewServer

        client = BrowserClient()
        live = LiveViewServer(client, port=18900)
        live.start()  # runs in background thread
    """

    def __init__(self, browser_client, port: int = 18900):
        self.browser_client = browser_client
        self.port = port
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._last_frame: Optional[bytes] = None
        self._last_frame_time: float = 0

    def _create_app(self):
        """Create the Flask application."""
        try:
            from flask import Flask, Response, send_file
        except ImportError:
            raise ImportError(
                "Flask is required for LiveView. Install with: pip install flask"
            )

        app = Flask(__name__)

        @app.route("/")
        def index():
            return Response(_LIVE_VIEW_HTML, content_type="text/html")

        @app.route("/frame")
        def frame():
            # Cache frames for 1 second to avoid overwhelming the browser
            now = time.time()
            if self._last_frame and (now - self._last_frame_time) < 1.0:
                return Response(self._last_frame, content_type="image/png")

            try:
                screenshot_bytes = self.browser_client.screenshot(format="png")
                self._last_frame = screenshot_bytes
                self._last_frame_time = now
                return Response(screenshot_bytes, content_type="image/png")
            except Exception as e:
                # Return a 1x1 transparent PNG on error
                return Response(
                    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
                    b'\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'
                    b'\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01'
                    b'\r\n\xb4\x00\x00\x00\x00IEND\xaeB`\x82',
                    content_type="image/png",
                    status=503,
                )

        @app.route("/health")
        def health():
            return {"status": "ok", "port": self.port}

        return app

    def start(self):
        """Start the LiveView server in a background thread."""
        if self._running:
            print(f"[LiveView] Already running on http://localhost:{self.port}")
            return

        app = self._create_app()
        self._running = True

        def _run():
            import logging
            log = logging.getLogger("werkzeug")
            log.setLevel(logging.ERROR)  # Suppress Flask request logs

            try:
                app.run(
                    host="127.0.0.1",
                    port=self.port,
                    debug=False,
                    use_reloader=False,
                    threaded=True,
                )
            except Exception as e:
                print(f"[LiveView] Server error: {e}")
            finally:
                self._running = False

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

        # Wait briefly for server to start
        time.sleep(0.5)
        print(f"[LiveView] 🔭 Visual rendering at http://localhost:{self.port}")

    def stop(self):
        """Stop the LiveView server."""
        self._running = False
        print("[LiveView] Stopped.")

    @property
    def is_running(self) -> bool:
        return self._running
