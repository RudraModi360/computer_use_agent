"""
Browser Tool — LLM-callable tool for browser automation.

Wraps BrowserClient into a single `browser_action()` function that can
be registered in the ToolRegistry for LLM tool-calling.
"""

import os
import json
import time
import tempfile
from typing import Optional

from nexus.config import config
from nexus.browser.browser_client import BrowserClient
from nexus.browser.chrome_launcher import ChromeLauncher

# Module-level singletons (shared across calls)
_browser_client: Optional[BrowserClient] = None
_chrome_launcher: Optional[ChromeLauncher] = None


def _get_client() -> BrowserClient:
    """Get or create the browser client singleton."""
    global _browser_client
    if _browser_client is None:
        _browser_client = BrowserClient(
            base_url=config.BROWSER_CONTROL_URL,
            auth_token=config.BROWSER_AUTH_TOKEN,
            profile=config.BROWSER_PROFILE,
        )
    return _browser_client


def _get_launcher() -> ChromeLauncher:
    """Get or create the Chrome launcher singleton."""
    global _chrome_launcher
    if _chrome_launcher is None:
        _chrome_launcher = ChromeLauncher(
            cdp_port=config.BROWSER_CDP_PORT,
            headless=config.BROWSER_HEADLESS,
        )
    return _chrome_launcher


def browser_action(
    action: str,
    url: str = "",
    ref: str = "",
    text: str = "",
    key: str = "",
    target_id: str = "",
    js_code: str = "",
    full_page: bool = False,
    submit: bool = False,
    file_path: str = "",
) -> str:
    """
    Control a web browser to navigate pages, click elements, type text, and more.
    
    Use this tool to interact with websites. First use 'snapshot' to see the page structure,
    then use element refs (e1, e2, etc.) to interact with elements.
    
    Workflow:
    1. 'launch' - Start Chrome browser (do this first if browser isn't running)
    2. 'navigate' - Go to a URL
    3. 'snapshot' - Get page structure with element refs
    4. 'click' / 'type' / 'press' - Interact with elements using refs
    5. 'screenshot' - Capture visual screenshot
    
    Args:
        action: Action to perform. One of:
            'launch' - Start Chrome browser
            'navigate' - Go to URL (requires url)
            'snapshot' - Get page structure (element refs)
            'click' - Click element (requires ref, e.g. 'e3')
            'type' - Type text into element (requires ref and text)
            'press' - Press keyboard key (requires key, e.g. 'Enter')
            'hover' - Hover over element (requires ref)
            'scroll' - Scroll element into view (requires ref)
            'screenshot' - Capture page screenshot
            'tabs' - List open tabs
            'open_tab' - Open new tab (optional url)
            'close_tab' - Close tab (requires target_id)
            'evaluate' - Run JavaScript (requires js_code)
            'wait' - Wait for text to appear (requires text)
            'status' - Check browser status
        url: URL for navigate/open_tab actions
        ref: Element reference from snapshot (e.g. 'e1', 'e3')
        text: Text for type/wait actions
        key: Key for press action (e.g. 'Enter', 'Escape', 'Tab')
        target_id: Tab target ID for multi-tab operations
        js_code: JavaScript code for evaluate action
        full_page: Whether screenshot should capture full page
        submit: Whether to press Enter after typing
        file_path: File path for saving screenshots
    
    Returns:
        str: Result of the action (text description, JSON data, or file path)
    """
    try:
        tid = target_id if target_id else None
        
        # ── Launch Chrome ─────────────────────────────────────────────
        if action == "launch":
            launcher = _get_launcher()
            cdp_url = launcher.launch(url=url or "about:blank")
            version = launcher.get_version()
            browser_name = version.get("Browser", "Unknown")
            return (
                f"Chrome launched successfully.\n"
                f"Browser: {browser_name}\n"
                f"CDP URL: {cdp_url}\n"
                f"You can now use 'navigate' to open a website."
            )

        # ── Status Check ──────────────────────────────────────────────
        elif action == "status":
            client = _get_client()
            launcher = _get_launcher()
            
            chrome_running = launcher.is_running()
            server_ok = client.health()
            
            parts = [f"Chrome CDP: {'Running' if chrome_running else 'Not running'}"]
            parts.append(f"OpenClaw Server: {'Connected' if server_ok else 'Not connected'}")
            
            if chrome_running:
                version = launcher.get_version()
                parts.append(f"Browser: {version.get('Browser', 'Unknown')}")
            
            if server_ok:
                try:
                    tabs = client.list_tabs()
                    parts.append(f"Open tabs: {len(tabs)}")
                    for t in tabs[:5]:
                        parts.append(f"  - [{t.get('targetId', '?')[:8]}] {t.get('title', 'Untitled')}")
                except Exception:
                    pass
            
            return "\n".join(parts)

        # ── Navigate ──────────────────────────────────────────────────
        elif action == "navigate":
            if not url:
                return "Error: 'url' is required for navigate action."
            client = _get_client()
            result = client.navigate(url, target_id=tid)
            return f"Navigated to: {result.get('url', url)}\nTab ID: {result.get('targetId', 'unknown')}"

        # ── Snapshot ──────────────────────────────────────────────────
        elif action == "snapshot":
            client = _get_client()
            snap = client.snapshot(target_id=tid)
            
            page_url = snap.get("url", "unknown")
            viewport = snap.get("viewport", {})
            snapshot_text = client.snapshot_text(target_id=tid)
            
            return (
                f"Page URL: {page_url}\n"
                f"Viewport: {viewport.get('width', '?')}x{viewport.get('height', '?')}\n"
                f"\n--- Page Structure ---\n{snapshot_text}\n"
                f"\nUse element refs (e.g. e1, e3) with click/type/hover actions."
            )

        # ── Click ─────────────────────────────────────────────────────
        elif action == "click":
            if not ref:
                return "Error: 'ref' is required for click action (e.g. ref='e3')."
            client = _get_client()
            client.click(ref, target_id=tid)
            return f"Clicked element [{ref}] successfully."

        # ── Type ──────────────────────────────────────────────────────
        elif action == "type":
            if not ref:
                return "Error: 'ref' is required for type action."
            if not text:
                return "Error: 'text' is required for type action."
            client = _get_client()
            client.type_text(ref, text, target_id=tid, submit=submit)
            submitted = " and submitted" if submit else ""
            return f"Typed '{text}' into element [{ref}]{submitted}."

        # ── Press Key ─────────────────────────────────────────────────
        elif action == "press":
            if not key:
                return "Error: 'key' is required for press action (e.g. 'Enter')."
            client = _get_client()
            client.press_key(key, target_id=tid)
            return f"Pressed key [{key}]."

        # ── Hover ─────────────────────────────────────────────────────
        elif action == "hover":
            if not ref:
                return "Error: 'ref' is required for hover action."
            client = _get_client()
            client.hover(ref, target_id=tid)
            return f"Hovering over element [{ref}]."

        # ── Scroll ────────────────────────────────────────────────────
        elif action == "scroll":
            if not ref:
                return "Error: 'ref' is required for scroll action."
            client = _get_client()
            client.scroll_into_view(ref, target_id=tid)
            return f"Scrolled element [{ref}] into view."

        # ── Screenshot ────────────────────────────────────────────────
        elif action == "screenshot":
            client = _get_client()
            img_bytes = client.screenshot(
                target_id=tid, full_page=full_page, format="png"
            )
            
            # Save to file
            save_path = file_path or os.path.join(
                tempfile.gettempdir(),
                f"agent-s-screenshot-{int(time.time())}.png"
            )
            with open(save_path, "wb") as f:
                f.write(img_bytes)
            
            size_kb = len(img_bytes) / 1024
            fp_label = "full page " if full_page else ""
            return (
                f"Screenshot saved: {save_path}\n"
                f"Size: {size_kb:.1f} KB ({fp_label}PNG)"
            )

        # ── Tabs ──────────────────────────────────────────────────────
        elif action == "tabs":
            client = _get_client()
            tabs = client.list_tabs()
            lines = [f"Open tabs ({len(tabs)}):"]
            for t in tabs:
                active_mark = " ★" if t.get("active") else ""
                lines.append(
                    f"  [{t.get('targetId', '?')[:12]}] "
                    f"{t.get('title', 'Untitled')}{active_mark}\n"
                    f"    URL: {t.get('url', '?')}"
                )
            return "\n".join(lines)

        # ── Open Tab ──────────────────────────────────────────────────
        elif action == "open_tab":
            client = _get_client()
            result = client.open_tab(url or "about:blank")
            return f"New tab opened.\nTab ID: {result.get('targetId', 'unknown')}\nURL: {result.get('url', url)}"

        # ── Close Tab ─────────────────────────────────────────────────
        elif action == "close_tab":
            if not target_id:
                return "Error: 'target_id' is required for close_tab action."
            client = _get_client()
            client.close_tab(target_id)
            return f"Tab [{target_id}] closed."

        # ── Evaluate JS ───────────────────────────────────────────────
        elif action == "evaluate":
            if not js_code:
                return "Error: 'js_code' is required for evaluate action."
            client = _get_client()
            result = client.evaluate_js(js_code, target_id=tid)
            return f"JavaScript result:\n{json.dumps(result, indent=2)}"

        # ── Wait ──────────────────────────────────────────────────────
        elif action == "wait":
            client = _get_client()
            if text:
                client.wait_for(target_id=tid, text=text)
                return f"Text '{text}' appeared on page."
            else:
                client.wait_for(target_id=tid, time_ms=2000)
                return "Waited 2 seconds."

        else:
            return (
                f"Error: Unknown action '{action}'.\n"
                f"Valid actions: launch, navigate, snapshot, click, type, press, "
                f"hover, scroll, screenshot, tabs, open_tab, close_tab, evaluate, "
                f"wait, status"
            )

    except ConnectionError as e:
        return (
            f"Browser connection error: {e}\n"
            f"Try using browser_action(action='launch') first, or check "
            f"that the OpenClaw browser server is running."
        )
    except Exception as e:
        return f"Browser action error: {e}"
