#!/usr/bin/env python3
"""
Advanced Agent Example - Auto Browser Controller
This agent automatically receives tab data and can control the browser via CDP
"""

import asyncio
import json
import websockets
import requests
from typing import Dict, List, Optional, Callable
from datetime import datetime
import time


class AutoBrowserAgent:
    """
    An agent that:
    1. Automatically receives tab updates from Chrome
    2. Maintains a live corpus of all tabs
    3. Can execute CDP commands to control the browser
    4. Makes autonomous decisions based on tab content
    """

    def __init__(self, base_url: str = "http://127.0.0.1:18792"):
        self.base_url = base_url
        self.ws_url = "ws://127.0.0.1:18792/client"
        self.ws = None
        self.corpus = []  # Live tab corpus
        self.is_running = False
        self.action_handlers = []

    def on_tab_collected(self, handler: Callable):
        """Register handler for when tabs are collected"""
        self.action_handlers.append(("tab_collected", handler))
        return handler

    def on_command_complete(self, handler: Callable):
        """Register handler for CDP command completion"""
        self.action_handlers.append(("command_complete", handler))
        return handler

    async def start(self):
        """Start the agent - connect to WebSocket and listen for events"""
        print("[Agent] Starting...")
        self.is_running = True

        # Connect to WebSocket
        self.ws = await websockets.connect(self.ws_url)
        print("[Agent] Connected to relay server")

        # Start listening for events
        await self._event_loop()

    async def _event_loop(self):
        """Main event loop - receives all tab data from Chrome"""
        try:
            async for message in self.ws:
                if not self.is_running:
                    break

                data = json.loads(message)
                await self._handle_event(data)

        except websockets.exceptions.ConnectionClosed:
            print("[Agent] Connection closed")
        except Exception as e:
            print(f"[Agent] Error: {e}")

    async def _handle_event(self, data: Dict):
        """Handle incoming events from Chrome"""
        event_type = data.get("type")
        event_data = data.get("data", {})

        if event_type == "tabDataQuick":
            # New tabs collected!
            tabs = event_data.get("tabs", [])
            print(f"\n[Agent] 📥 Received {len(tabs)} tabs from Chrome")

            # Add to corpus
            for tab in tabs:
                tab["received_at"] = datetime.now().isoformat()
                self.corpus.append(tab)

            # Call registered handlers
            for event, handler in self.action_handlers:
                if event == "tab_collected":
                    try:
                        await handler(tabs, self)
                    except Exception as e:
                        print(f"[Agent] Handler error: {e}")

            # Auto-analyze new tabs
            await self._analyze_tabs(tabs)

        elif event_type == "tabDataDeep":
            # Deep content received (DOM)
            tab = event_data.get("tab", {})
            print(f"[Agent] 📄 Deep content received: {tab.get('title', 'Unknown')}")

        elif event_type == "complete":
            print(f"[Agent] ✓ Collection complete: {event_data.get('totalTabs')} tabs")

        elif event_type == "event":
            # Tab lifecycle event (created/updated/removed)
            print(f"[Agent] 🔄 Tab event: {event_data.get('type')}")

    async def _analyze_tabs(self, tabs: List[Dict]):
        """Analyze new tabs and decide actions"""
        for tab in tabs:
            url = tab.get("url", "")
            title = tab.get("title", "")

            # Example: Find interesting tabs and interact with them
            if "github.com" in url:
                print(f"  🔍 Found GitHub tab: {title}")
                # Could trigger actions here

            elif "stackoverflow" in url:
                print(f"  ❓ Found StackOverflow: {title}")

            elif "docs" in url.lower() or "documentation" in url.lower():
                print(f"  📚 Found Documentation: {title}")

    # ============ CDP CONTROL METHODS ============

    async def execute_js(self, tab_id: int, script: str) -> Dict:
        """
        Execute JavaScript in a tab
        Example: await agent.execute_js(123, "document.title")
        """
        return await self._send_cdp_command(
            tab_id, "Runtime.evaluate", {"expression": script, "returnByValue": True}
        )

    async def click_element(self, tab_id: int, selector: str) -> Dict:
        """
        Click an element by CSS selector
        Example: await agent.click_element(123, "#submit-button")
        """
        script = f"""
            (function() {{
                var el = document.querySelector('{selector}');
                if (el) {{
                    el.click();
                    return 'clicked';
                }}
                return 'not found';
            }})()
        """
        return await self.execute_js(tab_id, script)

    async def fill_input(self, tab_id: int, selector: str, text: str) -> Dict:
        """
        Fill an input field
        Example: await agent.fill_input(123, "#search", "python tutorial")
        """
        script = f"""
            (function() {{
                var el = document.querySelector('{selector}');
                if (el) {{
                    el.value = '{text}';
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    return 'filled';
                }}
                return 'not found';
            }})()
        """
        return await self.execute_js(tab_id, script)

    async def scroll_page(
        self, tab_id: int, direction: str = "down", amount: int = 500
    ) -> Dict:
        """
        Scroll the page
        Example: await agent.scroll_page(123, "down", 800)
        """
        delta = amount if direction == "down" else -amount
        script = f"window.scrollBy(0, {delta}); return 'scrolled';"
        return await self.execute_js(tab_id, script)

    async def get_page_info(self, tab_id: int) -> Dict:
        """
        Get comprehensive page info
        Returns: title, url, scroll position, etc.
        """
        script = """
            (function() {
                return {
                    title: document.title,
                    url: window.location.href,
                    scrollX: window.scrollX,
                    scrollY: window.scrollY,
                    viewportHeight: window.innerHeight,
                    viewportWidth: window.innerWidth,
                    documentHeight: document.documentElement.scrollHeight,
                    links: Array.from(document.querySelectorAll('a')).slice(0, 10).map(a => ({
                        text: a.textContent.trim(),
                        href: a.href
                    })),
                    forms: document.querySelectorAll('form').length,
                    inputs: document.querySelectorAll('input').length,
                    buttons: document.querySelectorAll('button').length
                };
            })()
        """
        return await self.execute_js(tab_id, script)

    async def _send_cdp_command(self, tab_id: int, method: str, params: Dict) -> Dict:
        """Send CDP command via HTTP API"""
        try:
            response = requests.post(
                f"{self.base_url}/cdp/{tab_id}",
                json={"method": method, "params": params},
                timeout=30,
            )
            result = response.json()

            # Call completion handlers
            for event, handler in self.action_handlers:
                if event == "command_complete":
                    try:
                        await handler(method, result, self)
                    except:
                        pass

            return result
        except Exception as e:
            print(f"[Agent] CDP command failed: {e}")
            return {"error": str(e)}

    # ============ UTILITY METHODS ============

    def get_corpus(self) -> List[Dict]:
        """Get all collected tabs"""
        return self.corpus

    def find_tabs_by_url(self, pattern: str) -> List[Dict]:
        """Find tabs matching URL pattern"""
        return [t for t in self.corpus if pattern in t.get("url", "")]

    def find_tabs_by_title(self, pattern: str) -> List[Dict]:
        """Find tabs matching title pattern"""
        return [t for t in self.corpus if pattern in t.get("title", "")]

    def get_active_tabs(self) -> List[Dict]:
        """Get currently active tabs"""
        return [t for t in self.corpus if t.get("active", False)]

    async def refresh_corpus(self):
        """Manually trigger collection"""
        requests.post(f"{self.base_url}/collect")

    async def stop(self):
        """Stop the agent"""
        self.is_running = False
        if self.ws:
            await self.ws.close()
        print("[Agent] Stopped")


# ============ EXAMPLE USAGE ============


async def example_autonomous_agent():
    """
    Example: An agent that automatically collects tabs and interacts with them
    """
    agent = AutoBrowserAgent()

    # Register event handlers
    @agent.on_tab_collected
    async def on_new_tabs(tabs, agent):
        """Called whenever new tabs are collected"""
        print(f"\n[Handler] Processing {len(tabs)} new tabs...")

        # Find GitHub tabs and star them automatically (example)
        for tab in tabs:
            if (
                "github.com" in tab.get("url", "")
                and "star" not in tab.get("title", "").lower()
            ):
                print(f"  💡 Found GitHub repo: {tab.get('title')}")
                # In real use, you could:
                # await agent.click_element(tab['id'], ".star-button")

    @agent.on_command_complete
    async def on_command(method, result, agent):
        """Called when CDP command completes"""
        if method == "Runtime.evaluate":
            print(
                f"  ✓ JS execution result: {result.get('result', {}).get('value', 'N/A')[:100]}"
            )

    # Start the agent
    print("=" * 60)
    print("🤖 Auto Browser Agent Started")
    print("=" * 60)
    print("\nThe agent will now:")
    print("1. Automatically receive tab updates from Chrome")
    print("2. Store them in the corpus")
    print("3. Allow you to control the browser via CDP")
    print("\nPress Ctrl+C to stop\n")

    try:
        await agent.start()
    except KeyboardInterrupt:
        print("\n[Agent] Shutting down...")
        await agent.stop()


async def interactive_control_example():
    """
    Example: Interactive control of browser tabs
    Run this after agent has collected some tabs
    """
    agent = AutoBrowserAgent()

    print("=" * 60)
    print("🎮 Interactive Browser Control")
    print("=" * 60)

    # First, get current tabs
    response = requests.get("http://127.0.0.1:18792/tabs")
    tabs = response.json()

    if not tabs:
        print("\n❌ No tabs collected yet!")
        print("   Click the Chrome extension icon first")
        return

    print(f"\n📊 Found {len(tabs)} tabs in corpus:\n")

    for i, tab in enumerate(tabs[:10], 1):
        active = "🟢" if tab.get("active") else "⚪"
        print(f"{active} {i}. {tab.get('title', 'No title')[:50]}")
        print(f"      {tab.get('url', 'No URL')[:60]}...")

    # Example: Get detailed info from first tab
    if tabs:
        first_tab = tabs[0]
        tab_id = first_tab.get("tab_id")

        print(f"\n🔍 Getting detailed info from: {first_tab.get('title')}")
        info = await agent.get_page_info(tab_id)

        if "result" in info and "value" in info["result"]:
            page_data = info["result"]["value"]
            print(f"\n📄 Page Info:")
            print(f"   Title: {page_data.get('title')}")
            print(f"   URL: {page_data.get('url')}")
            print(f"   Scroll: {page_data.get('scrollY')}px")
            print(f"   Links: {len(page_data.get('links', []))}")
            print(f"   Forms: {page_data.get('forms')}")

            # Example: Scroll down
            print(f"\n📜 Scrolling down...")
            await agent.scroll_page(tab_id, "down", 500)
            print("   ✓ Scrolled 500px")


if __name__ == "__main__":
    import sys

    print("Chrome Tab Tracker - Advanced Agent")
    print("=" * 60)

    if len(sys.argv) > 1 and sys.argv[1] == "interactive":
        # Run interactive control
        asyncio.run(interactive_control_example())
    else:
        # Run autonomous agent
        print("\nModes:")
        print("  1. Auto mode (default): python3 auto_agent.py")
        print("  2. Interactive mode: python3 auto_agent.py interactive")
        print("\nStarting auto mode...\n")
        asyncio.run(example_autonomous_agent())
