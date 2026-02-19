# Chrome Tab Tracker - Quick Reference

## 🚀 Quick Start

```bash
# Terminal 1: Start relay server
cd ~/chrome-tracker
python3 relay_server.py

# Terminal 2: Load extension in Chrome
# 1. chrome://extensions/ → Developer mode ON
# 2. Load unpacked → Select ~/chrome-tracker/chrome-extension/
# 3. Click extension icon (blue circle)

# Terminal 3: Run agent
python3 test_agent.py        # Test connection
python3 auto_agent.py        # Full auto agent
python3 simple_integration.py # Simple example
```

## 📊 Data Flow

```
Chrome Extension → WebSocket → Relay Server → WebSocket → Your Agent
                      ↓
                SQLite Database (chrome_corpus.db)
```

## 📡 WebSocket Events (Agent Receives)

Your agent receives these events via WebSocket (`ws://127.0.0.1:18792/client`):

| Event Type | Data | When |
|------------|------|------|
| `tabDataQuick` | List of all tabs (id, url, title, etc.) | When you click extension |
| `tabDataDeep` | Full HTML + metadata for active tab | After quick data |
| `complete` | Total count, timestamp | Collection finished |
| `event` | Tab created/updated/removed | Real-time tab changes |

## 🎮 Controlling Browser (CDP)

Your agent can control Chrome via HTTP API:

```python
import requests

# Execute JavaScript
requests.post("http://127.0.0.1:18792/cdp/123", json={
    "method": "Runtime.evaluate",
    "params": {"expression": "document.title"}
})

# Available CDP commands:
# - Runtime.evaluate (execute JS)
# - Page.captureScreenshot
# - Page.getLayoutMetrics
# - And many more!
```

## 📁 File Overview

| File | Purpose |
|------|---------|
| `relay_server.py` | FastAPI server - keep this running |
| `agent_client.py` | Basic client library |
| `auto_agent.py` | Advanced agent with CDP control |
| `simple_integration.py` | Minimal integration example |
| `test_agent.py` | Test connection |
| `chrome-extension/` | Chrome extension files |

## 🗄️ Database

Stored in `chrome_corpus.db`:

```sql
-- tabs: metadata
SELECT * FROM tabs ORDER BY created_at DESC LIMIT 10;

-- tab_content: full HTML
SELECT url, title, LENGTH(html) as size FROM tab_content;

-- tab_events: lifecycle
SELECT * FROM tab_events WHERE event_type = 'created';
```

## 🔧 Troubleshooting

**Extension not connecting:**
```bash
# Check if server is running
curl http://127.0.0.1:18792/health

# Check extension console
# chrome://extensions/ → Click "service worker"
```

**Port already in use:**
```bash
# Kill existing server
pkill -f relay_server.py

# Or change port in extension options
```

**No data received:**
- Click the extension icon (blue circle) in Chrome
- Check extension service worker console for errors
- Verify port 18792 matches in extension options

## 💡 Usage Examples

### Example 1: Receive Tabs in Your Agent
```python
import asyncio
import websockets
import json

async def listen():
    async with websockets.connect("ws://127.0.0.1:18792/client") as ws:
        async for msg in ws:
            data = json.loads(msg)
            if data["type"] == "tabDataQuick":
                tabs = data["data"]["tabs"]
                print(f"Got {len(tabs)} tabs!")
                # Add to your corpus here

asyncio.run(listen())
```

### Example 2: Execute JavaScript
```python
import requests

# Click a button
requests.post("http://127.0.0.1:18792/cdp/123", json={
    "method": "Runtime.evaluate",
    "params": {
        "expression": "document.querySelector('#submit').click()"
    }
})
```

### Example 3: Search Corpus
```python
import requests

results = requests.get(
    "http://127.0.0.1:18792/search",
    params={"query": "python"}
).json()
```

## 🎯 Integration Checklist

- [ ] Start `relay_server.py` (keep running)
- [ ] Load extension in Chrome
- [ ] Click extension icon to collect tabs
- [ ] Connect agent to `ws://127.0.0.1:18792/client`
- [ ] Handle `tabDataQuick` events
- [ ] Add tab data to agent corpus
- [ ] Use CDP commands to control browser

## 📚 Next Steps

1. **Auto-collection**: Trigger collection periodically
2. **CDP automation**: Auto-click, fill forms, navigate
3. **Semantic search**: Vectorize content for similarity
4. **Screenshot capture**: Use `Page.captureScreenshot`
5. **Multi-tab control**: Execute commands across all tabs

## 🔗 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Server status |
| `/tabs` | GET | Get all tabs |
| `/content` | GET | Get tab content |
| `/search` | GET | Search corpus |
| `/collect` | POST | Trigger collection |
| `/cdp/{tab_id}` | POST | Execute CDP command |

## ⚡ Performance Tips

- Keep WebSocket connection open for real-time updates
- Use quick data for overview, deep data for details
- Query database directly for historical data
- Batch CDP commands when possible

---

**Need help?** Check the logs:
- Relay server terminal output
- Chrome extension service worker console
- HTTP responses from API calls