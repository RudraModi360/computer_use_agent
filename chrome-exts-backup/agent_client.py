"""
Chrome Tab Tracker - Agent Client
Simple client library for agents to interact with Chrome tabs
"""

import asyncio
import json
import websockets
import requests
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass
from datetime import datetime


@dataclass
class TabInfo:
    """Tab metadata"""

    id: int
    url: str
    title: str
    window_id: int
    active: bool
    pinned: bool
    timestamp: int


@dataclass
class TabContent:
    """Tab content with DOM"""

    id: int
    url: str
    title: str
    html: str
    text_content: str
    timestamp: int


class ChromeTabAgent:
    """Agent client for Chrome Tab Tracker"""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:18792",
        ws_url: str = "ws://127.0.0.1:18792/client",
    ):
        self.base_url = base_url
        self.ws_url = ws_url
        self.ws = None
        self.event_handlers: List[Callable] = []
        self.corpus_cache: List[Dict] = []

    def on_tab_data(self, handler: Callable):
        """Register handler for tab data events"""
        self.event_handlers.append(handler)
        return handler

    # HTTP API Methods

    def health_check(self) -> Dict:
        """Check if relay server is running"""
        response = requests.get(f"{self.base_url}/health")
        return response.json()

    def get_tabs(self, limit: int = 50) -> List[Dict]:
        """Get recent tabs from corpus"""
        response = requests.get(f"{self.base_url}/tabs", params={"limit": limit})
        return response.json()

    def get_content(self, url: Optional[str] = None, limit: int = 10) -> List[Dict]:
        """Get tab content/DOM from corpus"""
        params = {"limit": limit}
        if url:
            params["url"] = url
        response = requests.get(f"{self.base_url}/content", params=params)
        return response.json()

    def search_corpus(self, query: str) -> List[Dict]:
        """Search corpus for keywords"""
        response = requests.get(f"{self.base_url}/search", params={"query": query})
        return response.json()

    def trigger_collection(self) -> Dict:
        """Trigger tab collection from Chrome extension"""
        response = requests.post(f"{self.base_url}/collect")
        return response.json()

    def execute_cdp(
        self, tab_id: int, method: str, params: Optional[Dict] = None
    ) -> Dict:
        """Execute CDP command on specific tab"""
        payload = {"method": method}
        if params:
            payload["params"] = params
        response = requests.post(f"{self.base_url}/cdp/{tab_id}", json=payload)
        return response.json()

    # WebSocket Methods

    async def connect(self):
        """Connect to WebSocket for real-time updates"""
        self.ws = await websockets.connect(self.ws_url)
        asyncio.create_task(self._listen())

    async def disconnect(self):
        """Disconnect WebSocket"""
        if self.ws:
            await self.ws.close()
            self.ws = None

    async def _listen(self):
        """Listen for WebSocket messages"""
        try:
            async for message in self.ws:
                data = json.loads(message)
                await self._handle_event(data)
        except websockets.exceptions.ConnectionClosed:
            print("[Agent] WebSocket connection closed")

    async def _handle_event(self, data: Dict):
        """Handle incoming events"""
        event_type = data.get("type")
        event_data = data.get("data", {})

        # Cache the data
        self.corpus_cache.append(
            {
                "type": event_type,
                "data": event_data,
                "received_at": datetime.now().isoformat(),
            }
        )

        # Call registered handlers
        for handler in self.event_handlers:
            try:
                handler(event_type, event_data)
            except Exception as e:
                print(f"[Agent] Handler error: {e}")

    async def request_collection(self):
        """Request collection via WebSocket"""
        if self.ws:
            await self.ws.send(json.dumps({"method": "collect"}))

    # Utility Methods

    def is_relay_running(self) -> bool:
        """Check if relay server is available"""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=2)
            return response.status_code == 200
        except:
            return False

    def is_extension_connected(self) -> bool:
        """Check if Chrome extension is connected"""
        try:
            health = self.health_check()
            return health.get("extension_connected", False)
        except:
            return False

    def get_corpus_summary(self) -> Dict:
        """Get summary of collected corpus"""
        tabs = self.get_tabs(limit=1000)
        content = self.get_content(limit=1000)

        urls = set()
        domains = {}

        for tab in tabs:
            url = tab.get("url", "")
            urls.add(url)

            # Extract domain
            try:
                from urllib.parse import urlparse

                domain = urlparse(url).netloc
                domains[domain] = domains.get(domain, 0) + 1
            except:
                pass

        return {
            "total_tabs_collected": len(tabs),
            "unique_urls": len(urls),
            "tabs_with_content": len(content),
            "top_domains": sorted(domains.items(), key=lambda x: x[1], reverse=True)[
                :10
            ],
            "latest_collection": tabs[0].get("created_at") if tabs else None,
        }

    def export_corpus(self, filepath: str):
        """Export corpus to JSON file"""
        tabs = self.get_tabs(limit=10000)
        content = self.get_content(limit=10000)

        export_data = {
            "exported_at": datetime.now().isoformat(),
            "tabs": tabs,
            "content": content,
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

        print(f"[Agent] Corpus exported to {filepath}")


# Example usage
async def example_usage():
    """Example of how to use the agent client"""
    agent = ChromeTabAgent()

    # Check connection
    if not agent.is_relay_running():
        print(
            "[Agent] Relay server is not running. Start it with: python relay_server.py"
        )
        return

    if not agent.is_extension_connected():
        print(
            "[Agent] Extension not connected. Make sure Chrome extension is loaded and clicked."
        )

    # Trigger collection
    print("[Agent] Triggering tab collection...")
    result = agent.trigger_collection()
    print(f"[Agent] Result: {result}")

    # Wait a bit for collection
    await asyncio.sleep(2)

    # Get collected tabs
    tabs = agent.get_tabs(limit=50)
    print(f"[Agent] Collected {len(tabs)} tabs")

    for tab in tabs[:5]:
        print(
            f"  - {tab.get('title', 'No title')} | {tab.get('url', 'No URL')[:60]}..."
        )

    # Get detailed content
    content = agent.get_content(limit=5)
    print(f"\n[Agent] Retrieved {len(content)} tab contents")

    for item in content[:3]:
        text = item.get("text_content", "")[:200]
        print(f"\n  {item.get('title', 'No title')}:")
        print(f"  {text}...")

    # Search corpus
    results = agent.search_corpus("python")
    print(f"\n[Agent] Found {len(results)} results for 'python'")

    # Get summary
    summary = agent.get_corpus_summary()
    print(f"\n[Agent] Corpus Summary:")
    print(f"  Total tabs: {summary['total_tabs_collected']}")
    print(f"  Unique URLs: {summary['unique_urls']}")
    print(f"  Tabs with content: {summary['tabs_with_content']}")


if __name__ == "__main__":
    print("Chrome Tab Tracker Agent Client")
    print("=" * 50)
    print("\nRunning example usage...")
    asyncio.run(example_usage())
