"""
Chrome Tab Tracker - Python Relay Server
Receives tab data from Chrome extension and provides API for agents
"""

import asyncio
import json
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, List, Optional, Any, Set
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn


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
    """SQLite database for storing tab corpus"""

    def __init__(self, db_path: str = "chrome_corpus.db"):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

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

        conn.commit()
        conn.close()

    def store_quick_data(self, tabs: List[Dict]):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        for tab in tabs:
            cursor.execute(
                """
                INSERT INTO tabs (tab_id, url, title, window_id, active, pinned, fav_icon_url, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    tab.get("id"),
                    tab.get("url"),
                    tab.get("title"),
                    tab.get("windowId"),
                    tab.get("active", False),
                    tab.get("pinned", False),
                    tab.get("favIconUrl"),
                    tab.get("timestamp", int(datetime.now().timestamp() * 1000)),
                ),
            )

        conn.commit()
        conn.close()

    def store_deep_data(self, tab: Dict):
        import re

        # Extract text content from HTML
        html = tab.get("html", "")
        text_content = re.sub(r"<[^>]+>", " ", html)
        text_content = re.sub(r"\s+", " ", text_content).strip()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO tab_content (tab_id, url, title, html, text_content, layout_metrics, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
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

        conn.commit()
        conn.close()

    def store_event(self, event_type: str, tab_id: int, data: Dict):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO tab_events (event_type, tab_id, data, timestamp)
            VALUES (?, ?, ?, ?)
        """,
            (
                event_type,
                tab_id,
                json.dumps(data),
                int(datetime.now().timestamp() * 1000),
            ),
        )

        conn.commit()
        conn.close()

    def get_recent_tabs(self, limit: int = 50) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT * FROM tabs ORDER BY created_at DESC LIMIT ?
        """,
            (limit,),
        )

        columns = [description[0] for description in cursor.description]
        results = []

        for row in cursor.fetchall():
            results.append(dict(zip(columns, row)))

        conn.close()
        return results

    def get_tab_content(self, url: str = None, limit: int = 10) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if url:
            cursor.execute(
                """
                SELECT * FROM tab_content WHERE url = ? ORDER BY created_at DESC LIMIT ?
            """,
                (url, limit),
            )
        else:
            cursor.execute(
                """
                SELECT * FROM tab_content ORDER BY created_at DESC LIMIT ?
            """,
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

        conn.close()
        return results

    def search_corpus(self, query: str) -> List[Dict]:
        """Simple keyword search in text content"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT * FROM tab_content 
            WHERE text_content LIKE ? OR title LIKE ? OR url LIKE ?
            ORDER BY created_at DESC
        """,
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

        conn.close()
        return results


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    global corpus_db
    corpus_db = CorpusDatabase()
    print("[Relay Server] Started, database initialized")
    yield
    print("[Relay Server] Shutting down")


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
    if corpus_db is None:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return corpus_db.get_recent_tabs(limit)


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
        return await asyncio.wait_for(future, timeout=30.0)
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
