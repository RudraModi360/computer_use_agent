#!/usr/bin/env python3
"""
Simple Integration Example
Shows minimal code to receive tab data in your existing agent
"""

import asyncio
import json
import websockets
from typing import List, Dict


class SimpleAgentIntegration:
    """
    Minimal example - just receives tab data
    Add this to your existing agent codebase
    """

    def __init__(self):
        self.collected_tabs = []

    async def connect_and_listen(self):
        """Connect to Chrome Tab Tracker and receive data"""
        uri = "ws://127.0.0.1:18792/client"

        print("[Agent] Connecting to Chrome Tab Tracker...")
        async with websockets.connect(uri) as websocket:
            print("[Agent] Connected! Waiting for tab data...")
            print("[Agent] Click the Chrome extension icon to start collection\n")

            async for message in websocket:
                data = json.loads(message)
                await self.process_message(data)

    async def process_message(self, data: Dict):
        """Process incoming messages"""
        msg_type = data.get("type")
        msg_data = data.get("data", {})

        if msg_type == "tabDataQuick":
            tabs = msg_data.get("tabs", [])
            print(f"\n📥 Received {len(tabs)} tabs:")

            for tab in tabs:
                self.collected_tabs.append(tab)
                print(f"  • {tab.get('title', 'No title')[:60]}")
                print(f"    {tab.get('url', 'No URL')[:70]}...")

            # NOW: Pass to your agent's corpus
            self.add_to_corpus(tabs)

        elif msg_type == "tabDataDeep":
            tab = msg_data.get("tab", {})
            print(f"\n📄 Deep content for: {tab.get('title', 'Unknown')}")
            # Store HTML/text content
            self.add_content_to_corpus(tab)

        elif msg_type == "complete":
            print(f"\n✓ Collection complete: {msg_data.get('totalTabs')} tabs total")

    def add_to_corpus(self, tabs: List[Dict]):
        """
        ADD THIS TO YOUR AGENT:
        Store tabs in your agent's knowledge base/memory/corpus
        """
        # Example: Store in your agent's memory
        for tab in tabs:
            document = {
                "type": "web_page",
                "title": tab.get("title"),
                "url": tab.get("url"),
                "timestamp": tab.get("timestamp"),
                "source": "chrome_tracker",
            }
            # YOUR AGENT'S CODE HERE:
            # self.agent.memory.store(document)
            # self.agent.corpus.add(document)
            pass

        print(f"  ✓ Added {len(tabs)} documents to corpus")

    def add_content_to_corpus(self, tab: Dict):
        """Store full content to corpus"""
        document = {
            "type": "web_page_content",
            "title": tab.get("title"),
            "url": tab.get("url"),
            "html": tab.get("html", "")[:5000],  # First 5000 chars
            "text": tab.get("html", ""),  # Extracted text
            "timestamp": tab.get("timestamp"),
        }
        # YOUR AGENT'S CODE HERE
        print(f"  ✓ Added full content to corpus")


# ============ INTEGRATION TEMPLATE ============


class YourAgent:
    """
    Template showing how to integrate with your existing agent
    """

    def __init__(self):
        self.memory = []  # Your agent's memory
        self.chrome_tabs = []  # Chrome tabs corpus

    async def start_with_chrome_tracker(self):
        """
        Start your agent with Chrome Tab Tracker integration
        """
        # Start Chrome tracker listener in background
        tracker_task = asyncio.create_task(self._listen_to_chrome())

        # Start your agent's main loop
        await self.run()

    async def _listen_to_chrome(self):
        """Background task - listens for Chrome tab updates"""
        uri = "ws://127.0.0.1:18792/client"

        async with websockets.connect(uri) as ws:
            async for message in ws:
                data = json.loads(message)

                if data.get("type") == "tabDataQuick":
                    tabs = data["data"].get("tabs", [])

                    # Add to your agent's memory
                    for tab in tabs:
                        self.memory.append(
                            {
                                "role": "system",
                                "content": f"Browser tab: {tab.get('title')} - {tab.get('url')}",
                            }
                        )
                        self.chrome_tabs.append(tab)

                    print(f"[Agent] Added {len(tabs)} tabs to memory")

    async def run(self):
        """Your agent's main loop"""
        print("[Agent] Running with Chrome Tab Tracker...")
        print("[Agent] Click Chrome extension to collect tabs")

        while True:
            # Your agent's logic here
            await asyncio.sleep(1)


if __name__ == "__main__":
    print("Simple Chrome Tab Tracker Integration")
    print("=" * 50)
    print("\nThis shows how to receive tab data in your agent")
    print("\nUsage in your code:")
    print("  1. Connect to ws://127.0.0.1:18792/client")
    print("  2. Listen for messages")
    print("  3. Add tabs to your agent's corpus")
    print("\nStarting example...\n")

    try:
        integration = SimpleAgentIntegration()
        asyncio.run(integration.connect_and_listen())
    except KeyboardInterrupt:
        print("\n[Agent] Stopped")
