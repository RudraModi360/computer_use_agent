"""
BrowserClient — Python HTTP client for OpenClaw's Browser Control REST API.

Wraps every endpoint (tabs, navigate, act, snapshot, screenshot, storage, cookies)
into ergonomic Python methods with auto-retry and auth support.
"""

import json
import time
import base64
import requests
from typing import Optional, Dict, Any, List


class BrowserClient:
    """HTTP client for OpenClaw Browser Control Server."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:18791",
        auth_token: Optional[str] = None,
        profile: str = "openclaw",
        timeout: int = 30,
        retries: int = 2,
    ):
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self.profile = profile
        self.timeout = timeout
        self.retries = retries

    # ── Internal ──────────────────────────────────────────────────────

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers

    def _params(self, extra: Optional[Dict] = None) -> Dict[str, str]:
        params = {"profile": self.profile}
        if extra:
            params.update(extra)
        return params

    def _request(
        self, method: str, path: str,
        json_data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        raw: bool = False,
    ) -> Any:
        """Execute HTTP request with retry logic."""
        url = f"{self.base_url}{path}"
        merged_params = self._params(params)
        last_err = None

        for attempt in range(self.retries + 1):
            try:
                resp = requests.request(
                    method, url,
                    headers=self._headers(),
                    params=merged_params,
                    json=json_data,
                    timeout=self.timeout,
                )

                if raw:
                    return resp

                if resp.status_code == 401:
                    raise PermissionError(
                        "Authentication failed. Check your auth_token."
                    )

                resp.raise_for_status()
                return resp.json()

            except requests.ConnectionError as e:
                last_err = e
                if attempt < self.retries:
                    time.sleep(1)
                    continue
                raise ConnectionError(
                    f"Cannot connect to OpenClaw at {self.base_url}. "
                    f"Is the browser control server running? Error: {e}"
                ) from e

            except requests.Timeout as e:
                last_err = e
                if attempt < self.retries:
                    time.sleep(0.5)
                    continue
                raise TimeoutError(
                    f"Request to {url} timed out after {self.timeout}s"
                ) from e

        raise last_err

    def _get(self, path: str, **kw) -> Any:
        return self._request("GET", path, **kw)

    def _post(self, path: str, data: Optional[Dict] = None, **kw) -> Any:
        return self._request("POST", path, json_data=data, **kw)

    # ── Health ────────────────────────────────────────────────────────

    def health(self) -> bool:
        """Check if the browser control server is reachable."""
        try:
            resp = self._get("/health")
            return True
        except Exception:
            return False

    # ── Tab Management ────────────────────────────────────────────────

    def list_tabs(self) -> List[Dict]:
        """List all open browser tabs."""
        result = self._get("/tabs")
        return result.get("tabs", [])

    def open_tab(self, url: str = "about:blank") -> Dict:
        """Open a new tab with the given URL."""
        return self._post("/tabs", {"url": url})

    def focus_tab(self, target_id: str) -> Dict:
        """Focus/activate a tab by its target ID."""
        return self._post(f"/tabs/{target_id}/focus")

    def close_tab(self, target_id: str) -> Dict:
        """Close a tab by its target ID."""
        return self._post(f"/tabs/{target_id}/close")

    # ── Navigation ────────────────────────────────────────────────────

    def navigate(self, url: str, target_id: Optional[str] = None) -> Dict:
        """Navigate to a URL in the current or specified tab."""
        data = {"url": url}
        if target_id:
            data["targetId"] = target_id
        return self._post("/navigate", data)

    # ── Actions ───────────────────────────────────────────────────────

    def _act(self, kind: str, target_id: Optional[str] = None,
             **kwargs) -> Dict:
        """Execute a browser action."""
        data = {"kind": kind}
        if target_id:
            data["targetId"] = target_id
        data.update({k: v for k, v in kwargs.items() if v is not None})
        return self._post("/act", data)

    def click(self, ref: str, target_id: Optional[str] = None,
              double_click: bool = False, button: str = "left") -> Dict:
        """Click an element by its ref (e.g., 'e1', 'e3')."""
        return self._act(
            "click", target_id=target_id,
            ref=ref, doubleClick=double_click, button=button,
        )

    def type_text(self, ref: str, text: str,
                  target_id: Optional[str] = None,
                  submit: bool = False, slowly: bool = False) -> Dict:
        """Type text into an element."""
        return self._act(
            "type", target_id=target_id,
            ref=ref, text=text, submit=submit, slowly=slowly,
        )

    def press_key(self, key: str, target_id: Optional[str] = None) -> Dict:
        """Press a keyboard key (Enter, Escape, Tab, etc.)."""
        return self._act("press", target_id=target_id, key=key)

    def hover(self, ref: str, target_id: Optional[str] = None) -> Dict:
        """Hover over an element."""
        return self._act("hover", target_id=target_id, ref=ref)

    def scroll_into_view(self, ref: str,
                         target_id: Optional[str] = None) -> Dict:
        """Scroll an element into view."""
        return self._act("scrollIntoView", target_id=target_id, ref=ref)

    def drag(self, start_ref: str, end_ref: str,
             target_id: Optional[str] = None) -> Dict:
        """Drag from one element to another."""
        return self._act(
            "drag", target_id=target_id,
            startRef=start_ref, endRef=end_ref,
        )

    def select(self, ref: str, values: List[str],
               target_id: Optional[str] = None) -> Dict:
        """Select option(s) in a dropdown."""
        return self._act(
            "select", target_id=target_id,
            ref=ref, values=values,
        )

    def fill_form(self, fields: List[Dict],
                  target_id: Optional[str] = None) -> Dict:
        """
        Fill form fields.

        fields: list of {"ref": "e1", "type": "text", "value": "hello"}
        """
        return self._act("fill", target_id=target_id, fields=fields)

    def wait_for(self, target_id: Optional[str] = None,
                 time_ms: Optional[int] = None,
                 text: Optional[str] = None,
                 text_gone: Optional[str] = None,
                 selector: Optional[str] = None,
                 url: Optional[str] = None,
                 load_state: Optional[str] = None) -> Dict:
        """Wait for a condition on the page."""
        return self._act(
            "wait", target_id=target_id,
            timeMs=time_ms, text=text, textGone=text_gone,
            selector=selector, url=url, loadState=load_state,
        )

    def evaluate_js(self, js_code: str,
                    target_id: Optional[str] = None) -> Dict:
        """Execute JavaScript in the page context."""
        return self._act("evaluate", target_id=target_id, fn=js_code)

    def resize_viewport(self, width: int, height: int,
                        target_id: Optional[str] = None) -> Dict:
        """Resize the browser viewport."""
        return self._act(
            "resize", target_id=target_id,
            width=width, height=height,
        )

    # ── Snapshot ──────────────────────────────────────────────────────

    def snapshot(self, target_id: Optional[str] = None) -> Dict:
        """
        Get AI-optimized page snapshot (ARIA role tree).

        Returns semantic page structure with element refs (e1, e2, ...)
        that can be used for click/type/hover actions.
        """
        params = {}
        if target_id:
            params["targetId"] = target_id
        return self._get("/snapshot", params=params)

    # ── Screenshot ────────────────────────────────────────────────────

    def screenshot(self, target_id: Optional[str] = None,
                   full_page: bool = False,
                   format: str = "png",
                   quality: Optional[int] = None) -> bytes:
        """
        Capture a screenshot of the current page.
        Returns raw image bytes (PNG or JPEG).
        """
        data = {"fullPage": full_page, "format": format}
        if target_id:
            data["targetId"] = target_id
        if quality is not None:
            data["quality"] = quality

        resp = self._post("/screenshot", data, raw=True)
        resp.raise_for_status()
        return resp.content

    def screenshot_base64(self, **kwargs) -> str:
        """Capture screenshot and return as base64 string."""
        raw = self.screenshot(**kwargs)
        return base64.b64encode(raw).decode("utf-8")

    # ── Storage ───────────────────────────────────────────────────────

    def get_storage(self, target_id: Optional[str] = None) -> Dict:
        """Get localStorage and sessionStorage."""
        params = {}
        if target_id:
            params["targetId"] = target_id
        return self._get("/storage", params=params)

    def set_storage(self, local_storage: Optional[Dict] = None,
                    session_storage: Optional[Dict] = None,
                    target_id: Optional[str] = None) -> Dict:
        """Set localStorage and/or sessionStorage."""
        data = {}
        if local_storage:
            data["localStorage"] = local_storage
        if session_storage:
            data["sessionStorage"] = session_storage
        if target_id:
            data["targetId"] = target_id
        return self._post("/storage", data)

    # ── Cookies ───────────────────────────────────────────────────────

    def get_cookies(self) -> Dict:
        """Get all cookies for the current page."""
        return self._get("/cookies")

    def set_cookies(self, cookies: List[Dict]) -> Dict:
        """Set cookies."""
        return self._post("/cookies", {"cookies": cookies})

    # ── Convenience ───────────────────────────────────────────────────

    def snapshot_text(self, target_id: Optional[str] = None) -> str:
        """Get a human-readable text representation of the page snapshot."""
        snap = self.snapshot(target_id=target_id)
        role_tree = snap.get("roleSnapshot", {})

        lines = []
        self._flatten_snapshot(role_tree, lines, indent=0)
        return "\n".join(lines)

    def _flatten_snapshot(self, node: Dict, lines: List[str],
                          indent: int = 0) -> None:
        """Recursively flatten role snapshot tree to text."""
        prefix = "  " * indent
        role = node.get("role", "unknown")
        name = node.get("name", "")
        ref = node.get("ref", "")

        label = f"{prefix}[{ref}] {role}"
        if name:
            label += f': "{name}"'
        lines.append(label)

        for child in node.get("children", []):
            self._flatten_snapshot(child, lines, indent + 1)
