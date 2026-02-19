"""
Chrome Tab Tracker - Python Relay Server
Receives tab data from Chrome extension and provides API for agents

Optimized: persistent SQLite (WAL mode), async DB writes, reduced timeouts
"""

import asyncio
import json
import sqlite3
import time
import functools
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, List, Optional, Any, Set
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("relay.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("relay")


def timed(func):
    """Decorator to log execution time of functions."""
    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = await func(*args, **kwargs)
        elapsed = (time.perf_counter() - start) * 1000
        if elapsed > 50:  # Only log slow calls (>50ms)
            logger.info(f"[PERF] {func.__name__} took {elapsed:.1f}ms")
        return result
    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = (time.perf_counter() - start) * 1000
        if elapsed > 50:
            logger.info(f"[PERF] {func.__name__} took {elapsed:.1f}ms")
        return result
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper


# Request/Response models
class TabDataQuick(BaseModel):
    tabs: List[Dict[str, Any]]


class TabDataDeep(BaseModel):
    tab: Dict[str, Any]


class CollectionComplete(BaseModel):
    totalTabs: int
    timestamp: int


# Global state
extension_ws: Optional[WebSocket] = None
pending_requests: Dict[int, asyncio.Future] = {}
request_counter = 0
connected_clients: Set[WebSocket] = set()
corpus_db: Optional["CorpusDatabase"] = None


class CorpusDatabase:
    """SQLite database for storing tab corpus.
    
    Uses a single persistent connection with WAL mode for fast concurrent access.
    """

    def __init__(self, db_path: str = "chrome_corpus.db"):
        self.db_path = db_path
        # Single persistent connection — no per-call overhead
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA cache_size=-8000")  # 8MB cache
        self.conn.execute("PRAGMA temp_store=MEMORY")
        self.init_db()

    def init_db(self):
        cursor = self.conn.cursor()

        # Tabs table - stores metadata
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tabs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tab_id INTEGER,
                url TEXT,
                title TEXT,
                window_id INTEGER,
                active BOOLEAN,
                pinned BOOLEAN,
                fav_icon_url TEXT,
                timestamp INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Content table - stores DOM/content
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tab_content (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tab_id INTEGER,
                url TEXT,
                title TEXT,
                html TEXT,
                text_content TEXT,
                layout_metrics TEXT,
                timestamp INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Events table - tracks tab lifecycle
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tab_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT,
                tab_id INTEGER,
                data TEXT,
                timestamp INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Index for faster lookups
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tabs_tab_id ON tabs(tab_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tabs_created ON tabs(created_at DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_content_url ON tab_content(url)")

        self.conn.commit()

    @timed
    def store_quick_data(self, tabs: List[Dict]):
        cursor = self.conn.cursor()
        # Use executemany for batch insert — much faster
        data = [
            (
                tab.get("id"),
                tab.get("url"),
                tab.get("title"),
                tab.get("windowId"),
                tab.get("active", False),
                tab.get("pinned", False),
                tab.get("favIconUrl"),
                tab.get("timestamp", int(datetime.now().timestamp() * 1000)),
            )
            for tab in tabs
        ]
        cursor.executemany(
            "INSERT INTO tabs (tab_id, url, title, window_id, active, pinned, fav_icon_url, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            data,
        )
        self.conn.commit()

    @timed
    def store_deep_data(self, tab: Dict):
        import re

        # Extract text content from HTML
        html = tab.get("html", "")
        text_content = re.sub(r"<[^>]+>", " ", html)
        text_content = re.sub(r"\s+", " ", text_content).strip()

        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO tab_content (tab_id, url, title, html, text_content, layout_metrics, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                tab.get("id"),
                tab.get("url"),
                tab.get("title"),
                html,
                text_content,
                json.dumps(tab.get("layoutMetrics", {})),
                tab.get("timestamp", int(datetime.now().timestamp() * 1000)),
            ),
        )
        self.conn.commit()

    def store_event(self, event_type: str, tab_id: int, data: Dict):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO tab_events (event_type, tab_id, data, timestamp) VALUES (?, ?, ?, ?)",
            (event_type, tab_id, json.dumps(data), int(datetime.now().timestamp() * 1000)),
        )
        self.conn.commit()

    def get_recent_tabs(self, limit: int = 50) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM tabs ORDER BY created_at DESC LIMIT ?", (limit,))
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_tab_content(self, url: str = None, limit: int = 10) -> List[Dict]:
        cursor = self.conn.cursor()
        if url:
            cursor.execute(
                "SELECT * FROM tab_content WHERE url = ? ORDER BY created_at DESC LIMIT ?",
                (url, limit),
            )
        else:
            cursor.execute(
                "SELECT * FROM tab_content ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        columns = [description[0] for description in cursor.description]
        results = []
        for row in cursor.fetchall():
            row_dict = dict(zip(columns, row))
            if row_dict.get("layout_metrics"):
                try:
                    row_dict["layout_metrics"] = json.loads(row_dict["layout_metrics"])
                except:
                    pass
            results.append(row_dict)
        return results

    def search_corpus(self, query: str) -> List[Dict]:
        """Simple keyword search in text content"""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM tab_content WHERE text_content LIKE ? OR title LIKE ? OR url LIKE ? ORDER BY created_at DESC",
            (f"%{query}%", f"%{query}%", f"%{query}%"),
        )
        columns = [description[0] for description in cursor.description]
        results = []
        for row in cursor.fetchall():
            row_dict = dict(zip(columns, row))
            if row_dict.get("layout_metrics"):
                try:
                    row_dict["layout_metrics"] = json.loads(row_dict["layout_metrics"])
                except:
                    pass
            results.append(row_dict)
        return results

    def close(self):
        """Close the persistent connection."""
        if self.conn:
            self.conn.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    global corpus_db
    corpus_db = CorpusDatabase()
    print("[Relay Server] Started, database initialized (WAL mode)")
    yield
    print("[Relay Server] Shutting down")
    if corpus_db:
        corpus_db.close()


app = FastAPI(title="Chrome Tab Tracker Relay", lifespan=lifespan)


# HTTP Endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "extension_connected": extension_ws is not None,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/")
async def root():
    return {"message": "Chrome Tab Tracker Relay Server", "version": "1.0.0"}


@app.get("/tabs")
async def get_tabs(limit: int = 50):
    """Get recent tabs from corpus"""
    try:
        if corpus_db is None:
            raise HTTPException(status_code=503, detail="Database not initialized")
        return corpus_db.get_recent_tabs(limit)
    except Exception as e:
        logger.error(f"Error in get_tabs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/content")
async def get_content(url: str = None, limit: int = 10):
    """Get tab content/DOM from corpus"""
    if corpus_db is None:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return corpus_db.get_tab_content(url, limit)


@app.get("/search")
async def search_corpus(query: str):
    """Search corpus for keywords"""
    if corpus_db is None:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return corpus_db.search_corpus(query)


@app.post("/collect")
async def trigger_collection():
    """Trigger tab collection from extension"""
    if extension_ws is None:
        raise HTTPException(status_code=503, detail="Extension not connected")

    # Send collect command to extension
    await send_to_extension("collectTabs", {})
    return {"status": "collection_triggered"}


@app.post("/activate-tab/{tab_id}")
async def activate_tab(tab_id: int):
    """Activate a tab and bring Chrome window to foreground"""
    if extension_ws is None:
        raise HTTPException(status_code=503, detail="Extension not connected")

    result = await send_request_to_extension("activateTab", {"tabId": tab_id})
    return result


class OpenTabRequest(BaseModel):
    url: str = "https://www.google.com"


@app.post("/open-tab")
async def open_tab(body: OpenTabRequest):
    """Open a new tab in Chrome"""
    if extension_ws is None:
        raise HTTPException(status_code=503, detail="Extension not connected")

    result = await send_request_to_extension("openNewTab", {"url": body.url})
    return result


class CDPRequest(BaseModel):
    method: str
    params: dict = {}


@app.post("/cdp/{tab_id}")
async def execute_cdp(tab_id: int, body: CDPRequest):
    """Execute CDP command on specific tab"""
    if extension_ws is None:
        raise HTTPException(status_code=503, detail="Extension not connected")

    result = await send_request_to_extension(
        "executeCDP", {"tabId": tab_id, "method": body.method, "params": body.params}
    )

    return result


# WebSocket Endpoints
@app.websocket("/extension")
async def extension_websocket(websocket: WebSocket):
    """WebSocket for Chrome extension"""
    global extension_ws
    await websocket.accept()
    extension_ws = websocket
    print("[Relay Server] Extension connected")

    try:
        while True:
            message = await websocket.receive_text()
            await handle_extension_message(message, websocket)
    except WebSocketDisconnect:
        print("[Relay Server] Extension disconnected")
        extension_ws = None
    except Exception as e:
        print(f"[Relay Server] Extension error: {e}")
        extension_ws = None


@app.websocket("/client")
async def client_websocket(websocket: WebSocket):
    """WebSocket for Python clients/agents"""
    await websocket.accept()
    connected_clients.add(websocket)
    print("[Relay Server] Client connected")

    try:
        while True:
            message = await websocket.receive_text()
            data = json.loads(message)
            # Handle client requests
            if data.get("method") == "collect":
                await trigger_collection()
                await websocket.send_json({"status": "triggered"})
    except WebSocketDisconnect:
        print("[Relay Server] Client disconnected")
    except Exception as e:
        print(f"[Relay Server] Client error: {e}")
    finally:
        connected_clients.discard(websocket)


async def handle_extension_message(message: str, ws: WebSocket):
    """Handle messages from Chrome extension"""
    global corpus_db

    try:
        data = json.loads(message)

        # Handle pong response
        if data.get("method") == "pong":
            return

        # Handle request responses
        if "id" in data and data["id"] in pending_requests:
            future = pending_requests.pop(data["id"])
            if "error" in data:
                future.set_exception(Exception(data["error"]))
            else:
                future.set_result(data.get("result"))
            return

        # Handle tab data from extension
        method = data.get("method")
        params = data.get("params", {})

        if method == "tabDataQuick":
            print(
                f"[Relay Server] Received quick data for {len(params.get('tabs', []))} tabs"
            )
            if corpus_db:
                corpus_db.store_quick_data(params["tabs"])
            # Broadcast to connected clients
            await broadcast_to_clients({"type": "tabDataQuick", "data": params})

        elif method == "tabDataDeep":
            print(
                f"[Relay Server] Received deep data for tab: {params.get('tab', {}).get('url', 'unknown')}"
            )
            if corpus_db:
                corpus_db.store_deep_data(params["tab"])
            await broadcast_to_clients({"type": "tabDataDeep", "data": params})

        elif method == "collectionComplete":
            print(f"[Relay Server] Collection complete: {params.get('totalTabs')} tabs")
            await broadcast_to_clients({"type": "complete", "data": params})

        elif method == "tabEvent":
            event_type = params.get("type")
            tab_id = params.get("tabId") or params.get("tab", {}).get("id")
            if corpus_db and tab_id:
                corpus_db.store_event(event_type, tab_id, params)
            await broadcast_to_clients({"type": "event", "data": params})

    except json.JSONDecodeError:
        print(f"[Relay Server] Invalid JSON: {message}")
    except Exception as e:
        print(f"[Relay Server] Error handling message: {e}")


async def send_to_extension(method: str, params: dict):
    """Send command to extension"""
    if extension_ws is None:
        raise Exception("Extension not connected")

    await extension_ws.send_json({"method": method, "params": params})


async def send_request_to_extension(method: str, params: dict) -> dict:
    """Send request to extension and wait for response"""
    global request_counter

    if extension_ws is None:
        raise Exception("Extension not connected")

    request_id = request_counter
    request_counter += 1

    future = asyncio.Future()
    pending_requests[request_id] = future

    try:
        await extension_ws.send_json(
            {"id": request_id, "method": method, "params": params}
        )

        # Wait for response with timeout
        return await asyncio.wait_for(future, timeout=10.0)
    except asyncio.TimeoutError:
        pending_requests.pop(request_id, None)
        raise Exception("Request timeout")
    except Exception as e:
        pending_requests.pop(request_id, None)
        raise


async def broadcast_to_clients(message: dict):
    """Broadcast message to all connected clients"""
    disconnected = set()

    for client in connected_clients:
        try:
            await client.send_json(message)
        except:
            disconnected.add(client)

    # Clean up disconnected clients
    for client in disconnected:
        connected_clients.discard(client)


if __name__ == "__main__":
    print("[Relay Server] Starting Chrome Tab Tracker Relay...")
    print("[Relay Server] Extension WebSocket: ws://127.0.0.1:18792/extension")
    print("[Relay Server] Client WebSocket: ws://127.0.0.1:18792/client")
    print("[Relay Server] HTTP API: http://127.0.0.1:18792")
    uvicorn.run(app, host="127.0.0.1", port=18792)
