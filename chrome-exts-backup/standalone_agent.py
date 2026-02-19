#!/usr/bin/env python3
"""
Standalone Chrome Control Agent
Works without Agentry - uses direct tool execution
"""

import asyncio
import json
import requests
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class TabInfo:
    id: int
    url: str
    title: str
    active: bool


class StandaloneChromeAgent:
    """
    A standalone agent for controlling Chrome without Agentry dependency.
    Provides the same Chrome control capabilities.
    """

    def __init__(self, base_url: str = "http://127.0.0.1:18792"):
        self.base_url = base_url
        self.corpus = []

    def get_all_tabs(self) -> List[TabInfo]:
        """Get all Chrome tabs"""
        try:
            response = requests.get(f"{self.base_url}/tabs", timeout=5)
            tabs_data = response.json()

            tabs = []
            for t in tabs_data:
                tabs.append(
                    TabInfo(
                        id=t.get("tab_id", 0),
                        url=t.get("url", ""),
                        title=t.get("title", "No title"),
                        active=t.get("active", False),
                    )
                )
            return tabs
        except Exception as e:
            print(f"Error: {e}")
            return []

    def search_tabs(self, query: str) -> List[TabInfo]:
        """Search tabs"""
        try:
            response = requests.get(
                f"{self.base_url}/search", params={"query": query}, timeout=5
            )
            results = response.json()

            tabs = []
            for r in results:
                tabs.append(
                    TabInfo(
                        id=r.get("tab_id", 0),
                        url=r.get("url", ""),
                        title=r.get("title", "No title"),
                        active=False,
                    )
                )
            return tabs
        except Exception as e:
            print(f"Error: {e}")
            return []

    def execute_js(self, tab_id: int, script: str) -> str:
        """Execute JavaScript in a tab"""
        try:
            response = requests.post(
                f"{self.base_url}/cdp/{tab_id}",
                json={
                    "method": "Runtime.evaluate",
                    "params": {"expression": script, "returnByValue": True},
                },
                timeout=10,
            )
            result = response.json()

            if "result" in result and "value" in result["result"]:
                value = result["result"]["value"]
                return str(value) if value is not None else "null"
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Error: {e}"

    def click(self, tab_id: int, selector: str) -> str:
        """Click an element"""
        script = f"document.querySelector('{selector}')?.click(); 'clicked'"
        return self.execute_js(tab_id, script)

    def fill(self, tab_id: int, selector: str, text: str) -> str:
        """Fill an input"""
        escaped = text.replace("'", "\\'")
        script = f"document.querySelector('{selector}').value = '{escaped}'; 'filled'"
        return self.execute_js(tab_id, script)

    def scroll(self, tab_id: int, amount: int = 500) -> str:
        """Scroll page"""
        return self.execute_js(
            tab_id, f"window.scrollBy(0, {amount}); 'scrolled {amount}px'"
        )

    def get_page_info(self, tab_id: int) -> Dict:
        """Get page information"""
        script = """
            ({
                title: document.title,
                url: window.location.href,
                scrollY: window.scrollY,
                height: document.documentElement.scrollHeight,
                links: document.querySelectorAll('a').length,
                inputs: document.querySelectorAll('input').length,
                buttons: document.querySelectorAll('button').length
            })
        """
        result = self.execute_js(tab_id, script)
        try:
            return json.loads(result)
        except:
            return {"result": result}

    def display_tabs(self, tabs: List[TabInfo]):
        """Display tabs nicely"""
        if not tabs:
            print("No tabs found")
            return

        print(f"\n{'=' * 80}")
        print(f"Found {len(tabs)} tabs:")
        print("=" * 80)

        for i, tab in enumerate(tabs, 1):
            active = "🟢 " if tab.active else "⚪ "
            print(f"\n{i}. {active}{tab.title}")
            print(f"   ID: {tab.id}")
            print(f"   URL: {tab.url[:70]}...")

        print(f"\n{'=' * 80}\n")

    def interactive(self):
        """Interactive mode"""
        print("\n" + "=" * 80)
        print("🤖 Standalone Chrome Control Agent")
        print("=" * 80)
        print("\nCommands:")
        print("  tabs, list           - Show all tabs")
        print("  search <query>       - Search tabs")
        print("  js <tab_id> <code>   - Execute JavaScript")
        print("  click <tab_id> <sel> - Click element")
        print("  fill <tab_id> <sel> <text> - Fill input")
        print("  scroll <tab_id> [amount] - Scroll page")
        print("  info <tab_id>        - Get page info")
        print("  collect              - Trigger new collection")
        print("  quit, exit           - Exit")
        print("\n" + "=" * 80 + "\n")

        while True:
            try:
                command = input("> ").strip()

                if not command:
                    continue

                parts = command.split(maxsplit=2)
                cmd = parts[0].lower()

                if cmd in ["quit", "exit", "q"]:
                    print("Goodbye!")
                    break

                elif cmd in ["tabs", "list", "ls"]:
                    tabs = self.get_all_tabs()
                    self.display_tabs(tabs)

                elif cmd == "search":
                    if len(parts) < 2:
                        print("Usage: search <query>")
                        continue
                    query = parts[1]
                    tabs = self.search_tabs(query)
                    self.display_tabs(tabs)

                elif cmd == "js":
                    if len(parts) < 3:
                        print("Usage: js <tab_id> <javascript_code>")
                        continue
                    tab_id = int(parts[1])
                    script = parts[2]
                    result = self.execute_js(tab_id, script)
                    print(f"\nResult: {result}\n")

                elif cmd == "click":
                    if len(parts) < 3:
                        print("Usage: click <tab_id> <css_selector>")
                        continue
                    tab_id = int(parts[1])
                    selector = parts[2]
                    result = self.click(tab_id, selector)
                    print(f"\n{result}\n")

                elif cmd == "fill":
                    if len(parts) < 3:
                        print("Usage: fill <tab_id> <css_selector> <text>")
                        continue
                    tab_id = int(parts[1])
                    rest = parts[2].split(maxsplit=1)
                    if len(rest) < 2:
                        print("Usage: fill <tab_id> <css_selector> <text>")
                        continue
                    selector, text = rest
                    result = self.fill(tab_id, selector, text)
                    print(f"\n{result}\n")

                elif cmd == "scroll":
                    if len(parts) < 2:
                        print("Usage: scroll <tab_id> [amount]")
                        continue
                    tab_id = int(parts[1])
                    amount = int(parts[2]) if len(parts) > 2 else 500
                    result = self.scroll(tab_id, amount)
                    print(f"\n{result}\n")

                elif cmd == "info":
                    if len(parts) < 2:
                        print("Usage: info <tab_id>")
                        continue
                    tab_id = int(parts[1])
                    info = self.get_page_info(tab_id)
                    print(f"\nPage Info:")
                    for key, value in info.items():
                        print(f"  {key}: {value}")
                    print()

                elif cmd == "collect":
                    try:
                        requests.post(f"{self.base_url}/collect", timeout=5)
                        print("\n✓ Collection triggered\n")
                    except Exception as e:
                        print(f"\nError: {e}\n")

                else:
                    print(f"Unknown command: {cmd}")
                    print("Type 'help' for available commands")

            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break
            except Exception as e:
                print(f"Error: {e}")


if __name__ == "__main__":
    agent = StandaloneChromeAgent()

    # Check connection
    try:
        response = requests.get("http://127.0.0.1:18792/health", timeout=2)
        if response.status_code == 200:
            print("✓ Connected to Chrome Tab Tracker relay")
        else:
            print("⚠ Relay server may not be running")
            print("  Start it with: python3 relay_server.py")
    except:
        print("❌ Cannot connect to relay server")
        print("   Start it with: python3 relay_server.py")
        exit(1)

    # Start interactive mode
    agent.interactive()
