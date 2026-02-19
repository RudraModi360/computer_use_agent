# Chrome Tab Tracker

A complete system for tracking and collecting Chrome tabs as corpus for AI agents, inspired by OpenClaw's architecture but simplified for Python agents.

## Architecture

```
Chrome Extension ←→ Python Relay Server ←→ Your Agent
     (JS)              (FastAPI)           (Python)
```

## Components

### 1. Chrome Extension (`chrome-extension/`)
- **manifest.json**: Extension configuration (Manifest V3)
- **background.js**: Service worker that collects tabs
- **options.html**: Configuration UI

**Features:**
- Collects all open tabs metadata instantly
- Deep DOM scraping for active tab via CDP
- Real-time WebSocket connection to Python server
- Tracks tab lifecycle (create/update/remove)

### 2. Python Relay Server (`relay_server.py`)
- FastAPI-based HTTP/WebSocket server
- SQLite database for corpus storage
- WebSocket endpoints for extension and clients
- REST API for querying collected data

**Endpoints:**
- `GET /health` - Health check
- `GET /tabs` - Get collected tabs
- `GET /content` - Get tab content/DOM
- `GET /search` - Search corpus
- `POST /collect` - Trigger collection
- `POST /cdp/{tab_id}` - Execute CDP command

**WebSockets:**
- `/extension` - Chrome extension connection
- `/client` - Agent client connections

### 3. Agent Client (`agent_client.py`)
- Simple Python library for agents
- HTTP API wrapper
- WebSocket real-time updates
- Corpus export utilities

## Quick Start

### Step 1: Install Python Dependencies

```bash
cd chrome-tracker
pip install -r requirements.txt
```

### Step 2: Start the Relay Server

```bash
python relay_server.py
```

Server will start on:
- HTTP: http://127.0.0.1:18792
- Extension WS: ws://127.0.0.1:18792/extension
- Client WS: ws://127.0.0.1:18792/client

### Step 3: Load Chrome Extension

1. Open Chrome and navigate to `chrome://extensions/`
2. Enable "Developer mode" (toggle in top right)
3. Click "Load unpacked"
4. Select the `chrome-tracker/chrome-extension/` folder
5. Note the Extension ID (you'll see it on the card)

### Step 4: Connect Extension

1. Click the extension icon in Chrome toolbar
2. It will connect to the Python relay server
3. Badge shows: ON (green) = connected

### Step 5: Use the Agent Client

```python
from agent_client import ChromeTabAgent

agent = ChromeTabAgent()

# Check connections
if agent.is_relay_running():
    print("Relay server is running")

if agent.is_extension_connected():
    print("Extension is connected")

# Trigger collection
agent.trigger_collection()

# Get collected tabs
tabs = agent.get_tabs()
for tab in tabs:
    print(f"{tab['title']} - {tab['url']}")

# Get DOM content
content = agent.get_content()
for item in content:
    print(f"{item['title']}")
    print(item['text_content'][:500])  # First 500 chars

# Search corpus
results = agent.search_corpus("python")

# Export all data
agent.export_corpus("corpus_export.json")
```

## Database Schema

The relay server stores data in `chrome_corpus.db`:

**tabs** - Tab metadata
- `id`, `tab_id`, `url`, `title`, `window_id`
- `active`, `pinned`, `fav_icon_url`, `timestamp`

**tab_content** - Full DOM content
- `id`, `tab_id`, `url`, `title`, `html`
- `text_content`, `layout_metrics`, `timestamp`

**tab_events** - Lifecycle events
- `id`, `event_type`, `tab_id`, `data`, `timestamp`

## API Reference

### HTTP Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Check server and extension status |
| `/tabs` | GET | Get recent tabs (limit param) |
| `/content` | GET | Get tab content (url, limit params) |
| `/search` | GET | Search corpus (query param) |
| `/collect` | POST | Trigger collection from extension |
| `/cdp/{tab_id}` | POST | Execute CDP command |

### WebSocket Protocol

**Extension → Server:**
```json
{
  "method": "tabDataQuick",
  "params": { "tabs": [...] }
}
```

**Server → Extension:**
```json
{
  "id": 1,
  "method": "collectTabs",
  "params": {}
}
```

## Configuration

Change the relay port:

1. Edit `chrome-extension/options.html` default value
2. Or open extension options and change port
3. Restart relay server with new port

## How It Works

### Tab Collection Flow

1. **User clicks extension icon** OR **Agent calls `/collect`**
2. Extension queries all tabs via `chrome.tabs.query()`
3. Sends quick metadata to Python relay immediately
4. Attaches debugger to active tab only (to avoid UI clutter)
5. Gets full DOM via CDP `Runtime.evaluate`
6. Sends deep data to Python relay
7. Stores in SQLite database
8. Broadcasts to all connected agent clients

### CDP Commands

The extension can execute CDP commands on attached tabs:

```python
# Take screenshot
agent.execute_cdp(tab_id, "Page.captureScreenshot")

# Execute JavaScript
agent.execute_cdp(tab_id, "Runtime.evaluate", {
    "expression": "document.title"
})

# Get page metrics
agent.execute_cdp(tab_id, "Page.getLayoutMetrics")
```

## Limitations

1. **Debugger Bar**: CDP usage shows "Chrome is being controlled by automated test software" bar
2. **Manual Activation**: Extension must be clicked manually (Chrome security requirement)
3. **Single Active Tab**: Deep DOM collection only for active tab (avoid overwhelming)
4. **Sleeping Tabs**: Discarded tabs may lose connection
5. **Cross-Origin**: Limited access to cross-origin iframes

## Troubleshooting

**Extension not connecting:**
- Check relay server is running: `python relay_server.py`
- Check port matches in extension options
- Look at Chrome DevTools (service worker console) for errors

**No data collected:**
- Ensure you clicked the extension icon
- Check browser console for errors
- Verify relay server shows "Extension connected"

**Permission errors:**
- Extension needs debugger permission (shows warning on install)
- Must enable Developer mode to load unpacked extension

## Comparison with OpenClaw

| Feature | OpenClaw | This Implementation |
|---------|----------|---------------------|
| Language | TypeScript | Python |
| CDP Mode | Extension + Direct | Extension only |
| Tab Access | Per-tab attach | All tabs instantly + deep for active |
| Database | Complex | Simple SQLite |
| Use Case | Full browser automation | Agent corpus collection |

## Next Steps

1. Add vector search for semantic similarity
2. Implement periodic auto-collection
3. Add tab categorization/classification
4. Build web UI for browsing corpus
5. Add screenshot capture support

## License

MIT - Inspired by OpenClaw architecture