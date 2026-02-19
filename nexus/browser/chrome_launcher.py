"""
Chrome Launcher — Manage Chrome lifecycle via subprocess.

Detects Chrome/Edge/Brave on Windows and launches with CDP flags,
providing a fully automated browser startup without requiring OpenClaw's
Node.js launcher.
"""

import os
import subprocess
import time
import tempfile
import signal
import requests
from typing import Optional, List


class ChromeLauncher:
    """Launch and manage a Chrome/Chromium browser with CDP enabled."""

    # Windows Chrome candidate paths
    WINDOWS_CANDIDATES = [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
    ]

    def __init__(self, cdp_port: int = 9222, headless: bool = False,
                 user_data_dir: Optional[str] = None):
        self.cdp_port = cdp_port
        self.headless = headless
        self.user_data_dir = user_data_dir or os.path.join(
            tempfile.gettempdir(), f"agent-s-chrome-{cdp_port}"
        )
        self._process: Optional[subprocess.Popen] = None
        self._executable: Optional[str] = None

    @classmethod
    def find_chrome(cls) -> Optional[str]:
        """Auto-detect Chrome/Edge/Brave executable on Windows."""
        for path in cls.WINDOWS_CANDIDATES:
            if os.path.isfile(path):
                return path

        # Fallback: try 'where' command
        try:
            result = subprocess.run(
                ["where", "chrome.exe"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().split("\n")[0].strip()
        except Exception:
            pass

        return None

    def _build_args(self) -> List[str]:
        """Build Chrome launch arguments with CDP flags."""
        args = [
            f"--remote-debugging-port={self.cdp_port}",
            f"--user-data-dir={self.user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-breakpad",
            "--disable-client-side-phishing-detection",
            "--disable-component-update",
            "--disable-default-apps",
            "--disable-dev-shm-usage",
            "--disable-features=TranslateUI",
            "--disable-hang-monitor",
            "--disable-ipc-flooding-protection",
            "--disable-popup-blocking",
            "--disable-prompt-on-repost",
            "--disable-renderer-backgrounding",
            "--force-color-profile=srgb",
            "--metrics-recording-only",
            "--safebrowsing-disable-auto-update",
        ]

        if self.headless:
            args.append("--headless=new")

        return args

    def is_running(self) -> bool:
        """Check if Chrome CDP is reachable on the configured port."""
        try:
            resp = requests.get(
                f"http://127.0.0.1:{self.cdp_port}/json/version",
                timeout=2
            )
            return resp.status_code == 200
        except Exception:
            return False

    def launch(self, url: str = "about:blank", timeout: int = 30) -> str:
        """
        Launch Chrome with CDP enabled. Returns the CDP URL.

        If Chrome is already running on the port, returns immediately.
        """
        if self.is_running():
            print(f"[ChromeLauncher] Chrome already running on port {self.cdp_port}")
            return f"http://127.0.0.1:{self.cdp_port}"

        # Find executable
        self._executable = self.find_chrome()
        if not self._executable:
            raise RuntimeError(
                "Chrome/Edge/Brave not found. Install Chrome or set the path manually."
            )

        print(f"[ChromeLauncher] Launching: {self._executable}")
        print(f"[ChromeLauncher] CDP Port: {self.cdp_port}")
        print(f"[ChromeLauncher] User Data: {self.user_data_dir}")

        args = [self._executable] + self._build_args() + [url]

        # Launch Chrome as a detached process
        self._process = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            if os.name == "nt" else 0,
        )

        # Wait for CDP to become available
        cdp_url = f"http://127.0.0.1:{self.cdp_port}"
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.is_running():
                print(f"[ChromeLauncher] Chrome ready at {cdp_url}")
                return cdp_url
            time.sleep(0.5)

        raise TimeoutError(
            f"Chrome did not start within {timeout}s on port {self.cdp_port}"
        )

    def kill(self):
        """Terminate the Chrome process."""
        if self._process:
            try:
                if os.name == "nt":
                    self._process.terminate()
                else:
                    os.kill(self._process.pid, signal.SIGTERM)
                self._process.wait(timeout=5)
                print("[ChromeLauncher] Chrome terminated.")
            except Exception as e:
                print(f"[ChromeLauncher] Error killing Chrome: {e}")
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None

    def get_version(self) -> dict:
        """Get Chrome version info via CDP."""
        try:
            resp = requests.get(
                f"http://127.0.0.1:{self.cdp_port}/json/version",
                timeout=3
            )
            return resp.json()
        except Exception as e:
            return {"error": str(e)}

    def __del__(self):
        self.kill()
