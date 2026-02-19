#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  Intelligent Browser Agent — ReAct Loop with Ollama Tool Calling           ║
║                                                                            ║
║  This agent can understand natural language instructions like:              ║
║    "Tecblic is my firm, fill my today's timesheet"                         ║
║    "Search Google for Python docs and open the first result"               ║
║    "Find the Odoo tab and click on the timesheet menu"                     ║
║                                                                            ║
║  Architecture:                                                             ║
║    1. OBSERVE  — Inspect browser state (tabs, page info, content)          ║
║    2. THINK    — LLM reasons about what to do next                         ║
║    3. ACT      — Execute browser actions (click, fill, scroll, JS)        ║
║    4. REFLECT  — Evaluate result and decide if goal is achieved            ║
║                                                                            ║
║  Model: gpt-oss:20b-cloud via Ollama (native tool calling)                ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import json
import time
import re
import sys
import requests
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "gpt-oss:20b-cloud"
RELAY_BASE_URL = "http://127.0.0.1:18792"
MAX_ITERATIONS = 25          # Safety limit per task
REQUEST_TIMEOUT = 60         # Ollama request timeout (seconds)
TOOL_TIMEOUT = 15            # Tool execution timeout (seconds)

# ─────────────────────────────────────────────────────────────────────────────
# Color helpers for terminal output
# ─────────────────────────────────────────────────────────────────────────────
class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    BLUE    = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN    = "\033[96m"
    WHITE   = "\033[97m"
    BG_DARK = "\033[48;5;235m"

def banner(text, color=C.CYAN):
    width = 72
    print(f"\n{color}{C.BOLD}{'━' * width}")
    print(f"  {text}")
    print(f"{'━' * width}{C.RESET}")

def log_think(text):
    print(f"  {C.MAGENTA}🧠 Think:{C.RESET} {C.DIM}{text}{C.RESET}")

def log_act(tool, args_summary):
    print(f"  {C.YELLOW}⚡ Act:{C.RESET}   {C.BOLD}{tool}{C.RESET}({C.DIM}{args_summary}{C.RESET})")

def log_observe(text):
    # Truncate long observations
    if len(text) > 300:
        text = text[:300] + "…"
    print(f"  {C.BLUE}👁 Observe:{C.RESET} {C.DIM}{text}{C.RESET}")

def log_result(text):
    print(f"  {C.GREEN}✅ Result:{C.RESET} {text}")

def log_error(text):
    print(f"  {C.RED}❌ Error:{C.RESET}  {text}")

def log_iter(n, total):
    print(f"\n  {C.CYAN}{'─' * 50}")
    print(f"  Step {n}/{total}")
    print(f"  {'─' * 50}{C.RESET}")


# ─────────────────────────────────────────────────────────────────────────────
# Browser Tool Definitions (for Ollama tool calling)
# ─────────────────────────────────────────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_all_tabs",
            "description": (
                "Get all open Chrome tabs with their titles, URLs, tab IDs and active status. "
                "Use this first to understand what the user has open in their browser. "
                "Returns a list of tabs. The tab_id is needed for other tools."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_tabs",
            "description": (
                "Search through open tabs for specific content by keyword. "
                "Use this when looking for a specific tab like 'find the Odoo tab' "
                "or 'search for timesheet'. Returns matching tabs with IDs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search term to look for in tab titles and URLs",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_page_info",
            "description": (
                "Get comprehensive information about a page including: title, URL, "
                "scroll position, list of links, forms, input fields, and buttons. "
                "Use this to understand page structure before interacting."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tab_id": {
                        "type": "integer",
                        "description": "The tab ID (get from get_all_tabs or search_tabs)",
                    }
                },
                "required": ["tab_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_page_interactive_elements",
            "description": (
                "Get all interactive elements on the page: buttons, links, inputs, "
                "selects, textareas with their CSS selectors, text content, types, "
                "and visibility. Use this to find elements you can click, fill, or interact with. "
                "This is more detailed than get_page_info for interaction planning."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tab_id": {
                        "type": "integer",
                        "description": "The tab ID",
                    }
                },
                "required": ["tab_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_visible_text",
            "description": (
                "Get the visible text content of the current page (what the user sees). "
                "Use this to read what's on the page, check form labels, read messages, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tab_id": {
                        "type": "integer",
                        "description": "The tab ID",
                    }
                },
                "required": ["tab_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "click_element",
            "description": (
                "Click an element on the page using a CSS selector. "
                "Use this to press buttons, follow links, open menus, select options. "
                "Examples: '#submit', '.btn-primary', 'a[href*=timesheet]', "
                "'button:contains(Save)', 'nav a:nth-child(3)'"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tab_id": {
                        "type": "integer",
                        "description": "The tab ID",
                    },
                    "selector": {
                        "type": "string",
                        "description": "CSS selector for the element to click",
                    },
                },
                "required": ["tab_id", "selector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fill_input",
            "description": (
                "Fill an input field, textarea, or form element with text. "
                "Use this to type into search boxes, form fields, text areas. "
                "The input events are dispatched so frameworks detect the change."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tab_id": {
                        "type": "integer",
                        "description": "The tab ID",
                    },
                    "selector": {
                        "type": "string",
                        "description": "CSS selector for the input field",
                    },
                    "text": {
                        "type": "string",
                        "description": "Text to enter into the field",
                    },
                },
                "required": ["tab_id", "selector", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scroll_page",
            "description": (
                "Scroll the page up or down to see more content or reach elements. "
                "Use direction 'down' or 'up'. Default scroll amount is 500 pixels."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tab_id": {
                        "type": "integer",
                        "description": "The tab ID",
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["up", "down"],
                        "description": "Direction to scroll",
                    },
                    "amount": {
                        "type": "integer",
                        "description": "Pixels to scroll (default 500)",
                    },
                },
                "required": ["tab_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_javascript",
            "description": (
                "Execute arbitrary JavaScript in a tab. Use this for advanced interactions: "
                "complex DOM queries, reading specific attributes, simulating keyboard events, "
                "waiting for elements, selecting dropdowns, or any action not covered by other tools. "
                "The script is evaluated and the return value is sent back."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tab_id": {
                        "type": "integer",
                        "description": "The tab ID",
                    },
                    "script": {
                        "type": "string",
                        "description": "JavaScript code to execute in the page context",
                    },
                },
                "required": ["tab_id", "script"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "navigate_to_url",
            "description": (
                "Navigate a tab to a specific URL. Use this to open websites, "
                "go to specific pages, or redirect the current tab."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tab_id": {
                        "type": "integer",
                        "description": "The tab ID",
                    },
                    "url": {
                        "type": "string",
                        "description": "The URL to navigate to",
                    },
                },
                "required": ["tab_id", "url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wait_for_page_load",
            "description": (
                "Wait for the page to finish loading after a navigation or click. "
                "Use this after clicking links or navigating to ensure the page is ready. "
                "Returns the new page title and URL once loaded."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tab_id": {
                        "type": "integer",
                        "description": "The tab ID",
                    },
                    "wait_seconds": {
                        "type": "integer",
                        "description": "Seconds to wait (default 3)",
                    },
                },
                "required": ["tab_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trigger_collection",
            "description": (
                "Trigger the Chrome extension to re-collect all tabs. "
                "Use this to refresh the tab list if you suspect it's stale."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_complete",
            "description": (
                "Call this when the task is fully completed or when you cannot proceed further. "
                "Provide a summary of what was accomplished."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Summary of what was done or why the task cannot be completed",
                    },
                    "success": {
                        "type": "boolean",
                        "description": "Whether the task was completed successfully",
                    },
                },
                "required": ["summary", "success"],
            },
        },
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Browser Tools Implementation (backed by Chrome relay server)
# ─────────────────────────────────────────────────────────────────────────────

class BrowserTools:
    """Low-level browser control via the Chrome Tab Tracker relay server."""

    def __init__(self, base_url: str = RELAY_BASE_URL):
        self.base_url = base_url
        self._overlay_injected = {}  # tab_id -> bool

    # ── helpers ──

    def _cdp(self, tab_id: int, method: str, params: dict = None) -> dict:
        """Execute a CDP command through the relay."""
        payload = {"method": method, "params": params or {}}
        resp = requests.post(
            f"{self.base_url}/cdp/{tab_id}",
            json=payload,
            timeout=TOOL_TIMEOUT,
        )
        return resp.json()

    def _eval_js(self, tab_id: int, expression: str) -> Any:
        """Evaluate JS expression and return the result value."""
        result = self._cdp(tab_id, "Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True,
        })
        if "error" in result:
            return f"Error: {result['error']}"
        if isinstance(result, dict) and "result" in result:
            inner = result["result"]
            if isinstance(inner, dict) and "value" in inner:
                return inner["value"]
            elif isinstance(inner, dict) and "result" in inner:
                deep = inner["result"]
                if isinstance(deep, dict) and "value" in deep:
                    return deep["value"]
        return result

    def check_extension(self) -> bool:
        """Check if the Chrome extension is connected to the relay."""
        try:
            resp = requests.get(f"{self.base_url}/health", timeout=3)
            return resp.json().get("extension_connected", False)
        except Exception:
            return False

    # ── Visual Feedback System ──

    OVERLAY_JS = r"""
    (function() {
        if (window.__agentOverlayReady) return 'Overlay already injected';
        window.__agentOverlayReady = true;

        // --- Stylesheet ---
        var style = document.createElement('style');
        style.id = '__agent_overlay_css';
        style.textContent = `
            @keyframes __agent_pulse {
                0%   { box-shadow: 0 0 0 0 rgba(255, 50, 50, 0.7); }
                50%  { box-shadow: 0 0 20px 10px rgba(255, 50, 50, 0.3); }
                100% { box-shadow: 0 0 0 0 rgba(255, 50, 50, 0); }
            }
            @keyframes __agent_fadeIn {
                from { opacity: 0; transform: translateY(20px); }
                to   { opacity: 1; transform: translateY(0); }
            }
            @keyframes __agent_fadeOut {
                from { opacity: 1; transform: translateY(0); }
                to   { opacity: 0; transform: translateY(-10px); }
            }
            @keyframes __agent_cursor_blink {
                0%, 100% { opacity: 1; }
                50%      { opacity: 0.3; }
            }
            .__agent_highlight {
                outline: 3px solid #FF3232 !important;
                outline-offset: 2px !important;
                animation: __agent_pulse 0.6s ease-out 2 !important;
                transition: outline 0.3s ease !important;
                position: relative !important;
                z-index: 999998 !important;
            }
            #__agent_toast_container {
                position: fixed;
                top: 16px;
                right: 16px;
                z-index: 999999;
                display: flex;
                flex-direction: column;
                gap: 8px;
                pointer-events: none;
                font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            }
            .__agent_toast {
                background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                color: #e0e0e0;
                padding: 12px 20px;
                border-radius: 10px;
                font-size: 13px;
                line-height: 1.4;
                max-width: 380px;
                border-left: 4px solid #FF3232;
                box-shadow: 0 8px 32px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.05);
                animation: __agent_fadeIn 0.3s ease-out;
                backdrop-filter: blur(8px);
            }
            .__agent_toast_header {
                display: flex;
                align-items: center;
                gap: 6px;
                margin-bottom: 4px;
                font-weight: 600;
                color: #FF6B6B;
                font-size: 11px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            .__agent_toast.--success { border-left-color: #4ADE80; }
            .__agent_toast.--success .__agent_toast_header { color: #4ADE80; }
            .__agent_toast.--info { border-left-color: #60A5FA; }
            .__agent_toast.--info .__agent_toast_header { color: #60A5FA; }
            #__agent_cursor {
                position: fixed;
                width: 20px;
                height: 20px;
                z-index: 999999;
                pointer-events: none;
                transition: left 0.4s cubic-bezier(0.4, 0, 0.2, 1), top 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            }
            #__agent_cursor svg {
                filter: drop-shadow(0 2px 4px rgba(0,0,0,0.5));
            }
            #__agent_cursor_label {
                position: absolute;
                left: 22px;
                top: 18px;
                background: #1a1a2e;
                color: #FF6B6B;
                font-size: 10px;
                font-family: 'Segoe UI', system-ui, sans-serif;
                padding: 2px 8px;
                border-radius: 4px;
                white-space: nowrap;
                font-weight: 600;
                letter-spacing: 0.3px;
                border: 1px solid rgba(255,50,50,0.3);
            }
        `;
        document.head.appendChild(style);

        // --- Toast container ---
        var container = document.createElement('div');
        container.id = '__agent_toast_container';
        document.body.appendChild(container);

        // --- Virtual cursor ---
        var cursor = document.createElement('div');
        cursor.id = '__agent_cursor';
        cursor.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24"><path d="M5 3l14 9-7 2-4 7z" fill="#FF3232" stroke="#fff" stroke-width="1.5"/></svg><span id="__agent_cursor_label">🤖 Agent</span>';
        cursor.style.display = 'none';
        document.body.appendChild(cursor);

        // --- Global API ---
        window.__agentShowToast = function(text, type, duration) {
            type = type || 'action';
            duration = duration || 3000;
            var toast = document.createElement('div');
            toast.className = '__agent_toast' + (type === 'success' ? ' --success' : type === 'info' ? ' --info' : '');
            var icon = type === 'success' ? '✅' : type === 'info' ? '👁' : '⚡';
            toast.innerHTML = '<div class="__agent_toast_header">' + icon + ' Agent ' + type + '</div>' + text;
            container.appendChild(toast);
            setTimeout(function() {
                toast.style.animation = '__agent_fadeOut 0.3s ease-in forwards';
                setTimeout(function() { toast.remove(); }, 300);
            }, duration);
        };

        window.__agentHighlight = function(selector, label) {
            var el = document.querySelector(selector);
            if (!el) return false;
            el.classList.add('__agent_highlight');
            el.scrollIntoView({ block: 'center', behavior: 'smooth' });

            // Move cursor to element
            var rect = el.getBoundingClientRect();
            var cur = document.getElementById('__agent_cursor');
            if (cur) {
                cur.style.display = 'block';
                cur.style.left = (rect.left + rect.width / 2) + 'px';
                cur.style.top = (rect.top + rect.height / 2) + 'px';
            }

            // Remove highlight after animation
            setTimeout(function() {
                el.classList.remove('__agent_highlight');
                if (cur) cur.style.display = 'none';
            }, 2500);
            return true;
        };

        window.__agentMoveCursor = function(x, y) {
            var cur = document.getElementById('__agent_cursor');
            if (cur) {
                cur.style.display = 'block';
                cur.style.left = x + 'px';
                cur.style.top = y + 'px';
            }
        };

        return 'Visual overlay injected successfully';
    })()
    """

    def _inject_overlay(self, tab_id: int):
        """Inject the visual overlay into a tab if not already done."""
        if self._overlay_injected.get(tab_id):
            return
        try:
            self._eval_js(tab_id, self.OVERLAY_JS)
            self._overlay_injected[tab_id] = True
        except Exception:
            pass  # Non-critical

    def _show_toast(self, tab_id: int, text: str, toast_type: str = "action", duration: int = 3000):
        """Show a toast notification on the page."""
        self._inject_overlay(tab_id)
        escaped = text.replace("'", "\\'")
        self._eval_js(tab_id, f"window.__agentShowToast && window.__agentShowToast('{escaped}', '{toast_type}', {duration})")

    def _highlight_element(self, tab_id: int, selector: str, label: str = ""):
        """Highlight an element with red glow and move cursor to it."""
        self._inject_overlay(tab_id)
        escaped_sel = selector.replace("'", "\\'")
        escaped_label = label.replace("'", "\\'")
        self._eval_js(tab_id, f"window.__agentHighlight && window.__agentHighlight('{escaped_sel}', '{escaped_label}')")
        time.sleep(0.6)  # Let the user see the highlight

    # ── tool implementations ──

    def get_all_tabs(self) -> str:
        try:
            resp = requests.get(f"{self.base_url}/tabs", timeout=5)
            tabs = resp.json()
            if not tabs:
                return "No tabs collected yet. Click the Chrome extension icon first."
            lines = [f"Found {len(tabs)} tabs:\n"]
            for i, t in enumerate(tabs[:30], 1):
                active = "🟢 " if t.get("active") else "⚪ "
                lines.append(
                    f"{i}. {active}{t.get('title', 'Untitled')}\n"
                    f"   ID: {t.get('tab_id', 'N/A')}\n"
                    f"   URL: {t.get('url', '')}\n"
                )
            if len(tabs) > 30:
                lines.append(f"... and {len(tabs) - 30} more tabs")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    def search_tabs(self, query: str) -> str:
        try:
            resp = requests.get(
                f"{self.base_url}/search",
                params={"query": query},
                timeout=5,
            )
            results = resp.json()
            if not results:
                # Fallback: search in /tabs endpoint
                resp2 = requests.get(f"{self.base_url}/tabs", timeout=5)
                all_tabs = resp2.json()
                q_lower = query.lower()
                results = [
                    t for t in all_tabs
                    if q_lower in t.get("title", "").lower()
                    or q_lower in t.get("url", "").lower()
                ]
            if not results:
                return f"No tabs found matching '{query}'"

            lines = [f"Found {len(results)} matching tabs:\n"]
            for i, t in enumerate(results[:10], 1):
                lines.append(
                    f"{i}. {t.get('title', 'Untitled')}\n"
                    f"   ID: {t.get('tab_id', 'N/A')}\n"
                    f"   URL: {t.get('url', '')[:100]}\n"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    def get_page_info(self, tab_id: int) -> str:
        js = """
        (function() {
            var links = Array.from(document.querySelectorAll('a')).slice(0, 15).map(function(a) {
                return {text: a.textContent.trim().substring(0, 80), href: a.href};
            });
            var forms = Array.from(document.querySelectorAll('form')).map(function(f) {
                var inputs = Array.from(f.querySelectorAll('input,textarea,select')).map(function(inp) {
                    return {
                        tag: inp.tagName.toLowerCase(),
                        type: inp.type || '',
                        name: inp.name || '',
                        id: inp.id || '',
                        placeholder: inp.placeholder || '',
                        value: inp.value || ''
                    };
                });
                return { action: f.action, method: f.method, inputs: inputs };
            });
            return {
                title: document.title,
                url: window.location.href,
                scrollY: window.scrollY,
                viewportHeight: window.innerHeight,
                documentHeight: document.documentElement.scrollHeight,
                linkCount: document.querySelectorAll('a').length,
                topLinks: links,
                forms: forms,
                inputCount: document.querySelectorAll('input').length,
                buttonCount: document.querySelectorAll('button').length,
                selectCount: document.querySelectorAll('select').length,
                textareaCount: document.querySelectorAll('textarea').length
            };
        })()
        """
        result = self._eval_js(tab_id, js)
        if isinstance(result, (dict, list)):
            return json.dumps(result, indent=2, ensure_ascii=False)
        return str(result)

    def get_page_interactive_elements(self, tab_id: int) -> str:
        js = """
        (function() {
            function getSelector(el) {
                if (el.id) return '#' + el.id;
                var path = [];
                var current = el;
                while (current && current.nodeType === 1) {
                    var selector = current.tagName.toLowerCase();
                    if (current.id) { path.unshift('#' + current.id); break; }
                    if (current.className && typeof current.className === 'string') {
                        var cls = current.className.trim().split(/\\s+/).filter(function(c) { return c.length > 0; }).slice(0, 2).join('.');
                        if (cls) selector += '.' + cls;
                    }
                    var parent = current.parentElement;
                    if (parent) {
                        var siblings = Array.from(parent.children).filter(function(c) { return c.tagName === current.tagName; });
                        if (siblings.length > 1) {
                            var idx = siblings.indexOf(current) + 1;
                            selector += ':nth-of-type(' + idx + ')';
                        }
                    }
                    path.unshift(selector);
                    current = current.parentElement;
                }
                return path.join(' > ');
            }

            function isVisible(el) {
                var rect = el.getBoundingClientRect();
                var style = window.getComputedStyle(el);
                return rect.width > 0 && rect.height > 0
                    && style.display !== 'none'
                    && style.visibility !== 'hidden'
                    && style.opacity !== '0';
            }

            var elements = [];
            var selectors = 'button, a[href], input, select, textarea, [role="button"], [role="link"], [role="menuitem"], [role="tab"], [onclick], [contenteditable="true"]';

            document.querySelectorAll(selectors).forEach(function(el, idx) {
                if (idx > 80) return;  // Limit
                var visible = isVisible(el);
                var text = (el.textContent || '').trim().substring(0, 80);
                var tag = el.tagName.toLowerCase();

                elements.push({
                    index: idx,
                    tag: tag,
                    type: el.type || el.getAttribute('role') || '',
                    id: el.id || '',
                    name: el.name || '',
                    text: text,
                    placeholder: el.placeholder || '',
                    href: el.href || '',
                    value: (tag === 'input' || tag === 'textarea' || tag === 'select') ? (el.value || '').substring(0, 50) : '',
                    selector: getSelector(el),
                    visible: visible,
                    ariaLabel: el.getAttribute('aria-label') || ''
                });
            });

            return elements;
        })()
        """
        result = self._eval_js(tab_id, js)
        if isinstance(result, list):
            # Format nicely
            lines = [f"Found {len(result)} interactive elements:\n"]
            for el in result:
                if not el.get("visible", True):
                    continue
                tag = el.get("tag", "?")
                etype = el.get("type", "")
                text = el.get("text", "")[:60]
                selector = el.get("selector", "")
                name = el.get("name", "")
                placeholder = el.get("placeholder", "")
                aria = el.get("ariaLabel", "")
                href = el.get("href", "")

                label = text or aria or placeholder or name or ""
                detail = f"type={etype}" if etype else ""
                if href:
                    detail += f" href={href[:60]}"

                lines.append(
                    f"  [{el.get('index')}] <{tag}> \"{label}\"  "
                    f"{detail}  selector=\"{selector}\""
                )
            return "\n".join(lines)
        return str(result)

    def get_visible_text(self, tab_id: int) -> str:
        js = """
        (function() {
            var body = document.body;
            if (!body) return 'No body element';
            // Get only visible text, skip scripts/styles
            var walker = document.createTreeWalker(body, NodeFilter.SHOW_TEXT, {
                acceptNode: function(node) {
                    var parent = node.parentElement;
                    if (!parent) return NodeFilter.FILTER_REJECT;
                    var tag = parent.tagName.toLowerCase();
                    if (tag === 'script' || tag === 'style' || tag === 'noscript') return NodeFilter.FILTER_REJECT;
                    var style = window.getComputedStyle(parent);
                    if (style.display === 'none' || style.visibility === 'hidden') return NodeFilter.FILTER_REJECT;
                    var text = node.textContent.trim();
                    if (text.length === 0) return NodeFilter.FILTER_REJECT;
                    return NodeFilter.FILTER_ACCEPT;
                }
            });
            var texts = [];
            var totalLength = 0;
            while (walker.nextNode() && totalLength < 5000) {
                var t = walker.currentNode.textContent.trim();
                if (t.length > 0) {
                    texts.push(t);
                    totalLength += t.length;
                }
            }
            return texts.join('\\n');
        })()
        """
        result = self._eval_js(tab_id, js)
        if isinstance(result, str):
            # Truncate
            if len(result) > 4000:
                result = result[:4000] + "\n... (truncated)"
            return result
        return str(result)

    def click_element(self, tab_id: int, selector: str) -> str:
        # Inject visual overlay & highlight before clicking
        self._inject_overlay(tab_id)
        self._show_toast(tab_id, f'Clicking: <b>{selector[:60]}</b>', 'action')
        self._highlight_element(tab_id, selector, 'click')

        escaped = selector.replace("'", "\\'").replace("\\", "\\\\")
        js = f"""
        (function() {{
            var el = document.querySelector('{escaped}');
            if (!el) {{
                // Try case-insensitive text match
                var all = document.querySelectorAll('button, a, [role=button], input[type=submit]');
                for (var i = 0; i < all.length; i++) {{
                    if (all[i].textContent.trim().toLowerCase().includes('{escaped}'.toLowerCase())) {{
                        el = all[i];
                        break;
                    }}
                }}
            }}
            if (el) {{
                el.scrollIntoView({{block: 'center'}});
                el.focus();
                // Flash highlight
                el.classList.add('__agent_highlight');
                el.click();
                var desc = '<' + el.tagName.toLowerCase() + '> "' + el.textContent.trim().substring(0, 50) + '"';
                window.__agentShowToast && window.__agentShowToast('Clicked: ' + desc, 'success', 2000);
                setTimeout(function() {{ el.classList.remove('__agent_highlight'); }}, 2000);
                return 'Clicked: ' + desc;
            }}
            window.__agentShowToast && window.__agentShowToast('Element not found: {escaped}', 'action', 3000);
            return 'Element not found: {escaped}';
        }})()
        """
        result = self._eval_js(tab_id, js)
        return str(result)

    def fill_input(self, tab_id: int, selector: str, text: str) -> str:
        # Inject visual overlay & highlight before filling
        self._inject_overlay(tab_id)
        self._show_toast(tab_id, f'Typing into: <b>{selector[:40]}</b><br>Text: "{text[:50]}"', 'action')
        self._highlight_element(tab_id, selector, 'fill')

        escaped_sel = selector.replace("'", "\\'").replace("\\", "\\\\")
        escaped_text = text.replace("'", "\\'").replace("\\", "\\\\").replace("\n", "\\n")
        js = f"""
        (function() {{
            var el = document.querySelector('{escaped_sel}');
            if (!el) {{
                window.__agentShowToast && window.__agentShowToast('Input not found: {escaped_sel}', 'action', 3000);
                return 'Input not found: {escaped_sel}';
            }}

            el.scrollIntoView({{block: 'center'}});
            el.focus();
            el.classList.add('__agent_highlight');

            // Clear existing value
            el.value = '';

            // Use native input setter for React/Angular/Vue compatibility
            var nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value'
            );
            var nativeTextareaValueSetter = Object.getOwnPropertyDescriptor(
                window.HTMLTextAreaElement.prototype, 'value'
            );
            var setter = el.tagName === 'TEXTAREA' ? nativeTextareaValueSetter : nativeInputValueSetter;
            if (setter && setter.set) {{
                setter.set.call(el, '{escaped_text}');
            }} else {{
                el.value = '{escaped_text}';
            }}

            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            el.dispatchEvent(new KeyboardEvent('keyup', {{ bubbles: true }}));

            var desc = 'Filled "' + (el.name || el.id || el.placeholder || el.tagName) + '" with: {text}';
            window.__agentShowToast && window.__agentShowToast(desc, 'success', 2500);
            setTimeout(function() {{ el.classList.remove('__agent_highlight'); }}, 2000);
            return desc;
        }})()
        """
        result = self._eval_js(tab_id, js)
        return str(result)

    def scroll_page(self, tab_id: int, direction: str = "down", amount: int = 500) -> str:
        self._inject_overlay(tab_id)
        self._show_toast(tab_id, f'Scrolling {direction} by {amount}px', 'info', 1500)
        delta = amount if direction == "down" else -amount
        js = f"""
        (function() {{
            var before = window.scrollY;
            window.scrollBy({{top: {delta}, behavior: 'smooth'}});
            var after = window.scrollY;
            return 'Scrolled {direction} by {amount}px (position: ' + Math.round(before) + ' → ' + Math.round(after) + ')';
        }})()
        """
        result = self._eval_js(tab_id, js)
        return str(result)

    def execute_javascript(self, tab_id: int, script: str) -> str:
        result = self._eval_js(tab_id, script)
        if isinstance(result, (dict, list)):
            return json.dumps(result, indent=2, ensure_ascii=False)
        return str(result)

    def navigate_to_url(self, tab_id: int, url: str) -> str:
        self._inject_overlay(tab_id)
        self._show_toast(tab_id, f'Navigating to:<br><b>{url[:60]}</b>', 'info', 2000)
        time.sleep(0.5)  # Let the user see the toast
        self._overlay_injected.pop(tab_id, None)  # Will need re-inject after nav
        js = f"window.location.href = '{url}'; 'Navigating to: {url}'"
        result = self._eval_js(tab_id, js)
        return str(result)

    def wait_for_page_load(self, tab_id: int, wait_seconds: int = 3) -> str:
        time.sleep(wait_seconds)
        js = """
        (function() {
            return {
                title: document.title,
                url: window.location.href,
                readyState: document.readyState
            };
        })()
        """
        result = self._eval_js(tab_id, js)
        if isinstance(result, dict):
            return json.dumps(result, indent=2)
        return str(result)

    def trigger_collection(self) -> str:
        try:
            resp = requests.post(f"{self.base_url}/collect", timeout=5)
            return "Collection triggered! Tab list will be refreshed in a moment."
        except Exception as e:
            return f"Error: {e}"

    def task_complete(self, summary: str, success: bool) -> str:
        return f"{'✅' if success else '❌'} TASK {'COMPLETE' if success else 'FAILED'}: {summary}"


# ─────────────────────────────────────────────────────────────────────────────
# Tool Router — maps names to functions
# ─────────────────────────────────────────────────────────────────────────────

def build_tool_router(tools: BrowserTools) -> Dict[str, Callable]:
    """Map tool names to their implementation functions."""
    return {
        "get_all_tabs": lambda **kw: tools.get_all_tabs(),
        "search_tabs": lambda **kw: tools.search_tabs(kw["query"]),
        "get_page_info": lambda **kw: tools.get_page_info(kw["tab_id"]),
        "get_page_interactive_elements": lambda **kw: tools.get_page_interactive_elements(kw["tab_id"]),
        "get_visible_text": lambda **kw: tools.get_visible_text(kw["tab_id"]),
        "click_element": lambda **kw: tools.click_element(kw["tab_id"], kw["selector"]),
        "fill_input": lambda **kw: tools.fill_input(kw["tab_id"], kw["selector"], kw["text"]),
        "scroll_page": lambda **kw: tools.scroll_page(
            kw["tab_id"], kw.get("direction", "down"), kw.get("amount", 500)
        ),
        "execute_javascript": lambda **kw: tools.execute_javascript(kw["tab_id"], kw["script"]),
        "navigate_to_url": lambda **kw: tools.navigate_to_url(kw["tab_id"], kw["url"]),
        "wait_for_page_load": lambda **kw: tools.wait_for_page_load(
            kw["tab_id"], kw.get("wait_seconds", 3)
        ),
        "trigger_collection": lambda **kw: tools.trigger_collection(),
        "task_complete": lambda **kw: tools.task_complete(
            kw["summary"], kw.get("success", True)
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# System Prompt
# ─────────────────────────────────────────────────────────────────────────────

def build_system_prompt() -> str:
    now = datetime.now()
    return f"""You are an intelligent browser automation agent. You control the user's Chrome browser to accomplish tasks they describe in natural language.

## Current Context
- **Date**: {now.strftime('%A, %B %d, %Y')}
- **Time**: {now.strftime('%I:%M %p')}
- **Timezone**: IST (India Standard Time)

## Your Capabilities
You have access to browser control tools that let you:
1. **See** — List tabs, read page content, inspect interactive elements
2. **Navigate** — Open URLs, switch between tabs
3. **Interact** — Click buttons/links, fill forms, scroll pages
4. **Execute** — Run arbitrary JavaScript for advanced interactions

## How to Work (ReAct Pattern)
For each step:
1. **Think** about what you need to do next based on the current state
2. **Act** by calling the appropriate tool
3. **Observe** the result
4. **Decide** if the task is done or if you need more steps

## Important Rules
1. **Always start by observing** — Use get_all_tabs to see what's open, then get_page_info or get_page_interactive_elements to understand the page
2. **Be precise with selectors** — Use get_page_interactive_elements to find the exact CSS selector before clicking/filling
3. **Wait after navigation** — After clicking links or navigating, use wait_for_page_load before inspecting the new page
4. **Handle errors gracefully** — If a selector doesn't work, try alternative approaches (different selector, JS execution)
5. **Fill forms completely** — When filling forms (like timesheets), fill ALL required fields
6. **Verify your actions** — After important actions, read the page to verify they succeeded
7. **Call task_complete** when done — Always end by calling task_complete with a summary

## Understanding User Intent
- The user may use informal language, typos, or abbreviations
- "Tecblic" / "tecblic" = the user's company (Tecblic Private Limited)
- "timesheet" = daily time tracking form, likely on Odoo ERP (internalerp.tecblic.com)
- "fill timesheet" = enter working hours for today
- Interpret the user's intent, don't ask for clarification — just do it

## Tips for Odoo/ERP Timesheets
- The Odoo timesheet URL is typically: internalerp.tecblic.com
- Look for "Timesheet" or similar menu items
- Timesheet forms usually have: Date, Description/Activity, Project, Hours fields
- Today's date should be pre-filled or auto-selected
- Standard work hours: 8 hours if not specified

## Tips for Form Interaction
- For date pickers, try clicking them and using JS to set the value
- For dropdowns/selects, use click to open + then select the option
- For Odoo forms, the fields often use specific class names like .o_field_widget, .o_input
- After filling a form, look for a Save button and click it"""


# ─────────────────────────────────────────────────────────────────────────────
# Ollama Chat Client (with tool calling)
# ─────────────────────────────────────────────────────────────────────────────

class OllamaChat:
    """Handles communication with Ollama API for chat + tool calling."""

    def __init__(
        self,
        model: str = OLLAMA_MODEL,
        base_url: str = OLLAMA_BASE_URL,
    ):
        self.model = model
        self.base_url = base_url

    def chat(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
    ) -> Dict:
        """Send chat request with optional tools, return the response message."""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.2,     # Low for more deterministic tool calls
                "num_predict": 2048,    # Enough for reasoning + tool calls
            },
        }
        if tools:
            payload["tools"] = tools

        resp = requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", {})


# ─────────────────────────────────────────────────────────────────────────────
# The Agent — ReAct Loop
# ─────────────────────────────────────────────────────────────────────────────

class IntelligentBrowserAgent:
    """
    ReAct (Reason + Act) agent for browser automation.

    Flow:
        User prompt → System prompt + tools → LLM reasons + calls tools →
        Tool results fed back → LLM continues → ... → task_complete
    """

    def __init__(self):
        self.llm = OllamaChat()
        self.browser = BrowserTools()
        self.tool_router = build_tool_router(self.browser)
        self.conversation: List[Dict] = []
        self.task_done = False

    def reset(self):
        """Reset state for a new task."""
        self.conversation = [{"role": "system", "content": build_system_prompt()}]
        self.task_done = False

    def execute_tool(self, name: str, arguments: Dict) -> str:
        """Execute a tool by name with given arguments and return result."""
        if name == "task_complete":
            self.task_done = True

        fn = self.tool_router.get(name)
        if fn is None:
            return f"Unknown tool: {name}"

        try:
            result = fn(**arguments)
            return str(result) if result is not None else "Done (no output)"
        except Exception as e:
            return f"Tool error ({name}): {str(e)}"

    def run_task(self, user_prompt: str) -> str:
        """
        Main entry: run the ReAct loop for a user prompt.
        Returns the final summary when complete.
        """
        self.reset()

        banner(f"Task: {user_prompt}", C.GREEN)
        print(f"  {C.DIM}Model: {OLLAMA_MODEL} | Max steps: {MAX_ITERATIONS}{C.RESET}\n")

        # Add user message
        self.conversation.append({"role": "user", "content": user_prompt})

        final_summary = ""
        text_only_rounds = 0   # Track consecutive text-only (no tool) rounds

        for iteration in range(1, MAX_ITERATIONS + 1):
            if self.task_done:
                break

            log_iter(iteration, MAX_ITERATIONS)

            # ── Ask LLM ──
            try:
                response = self.llm.chat(
                    messages=self.conversation,
                    tools=TOOL_DEFINITIONS,
                )
            except Exception as e:
                log_error(f"LLM request failed: {e}")
                time.sleep(2)
                continue

            # Extract thinking (chain of thought)
            thinking = response.get("thinking", "")
            content = response.get("content", "")
            tool_calls = response.get("tool_calls", [])

            if thinking:
                log_think(thinking[:200] + ("…" if len(thinking) > 200 else ""))

            if content and not tool_calls:
                # LLM is giving a text response (no tool call)
                text_only_rounds += 1
                print(f"  {C.WHITE}💬 Agent:{C.RESET} {content[:300]}")
                self.conversation.append({"role": "assistant", "content": content})

                # If too many text-only rounds, auto-complete
                if text_only_rounds >= 2:
                    final_summary = content[:200]
                    self.task_done = True
                    log_result(f"(Auto-completed) {final_summary}")
                    break

                # Nudge the LLM to use tools, referencing original task
                if not self.task_done:
                    self.conversation.append({
                        "role": "user",
                        "content": (
                            f"You must use the browser tools to complete the original task: "
                            f"\"{user_prompt}\". "
                            f"Do NOT just talk about it — call a tool now. "
                            f"Start with get_all_tabs if you haven't already. "
                            f"When done, call task_complete."
                        ),
                    })
                continue

            if not tool_calls:
                text_only_rounds += 1
                log_error("No tool calls and no content from LLM")
                if text_only_rounds >= 3:
                    final_summary = "Agent failed to produce tool calls."
                    self.task_done = True
                    break
                self.conversation.append({
                    "role": "user",
                    "content": f"Please call a tool now to work on: \"{user_prompt}\"",
                })
                continue

            # Reset text-only counter when we get tool calls
            text_only_rounds = 0

            # ── Execute tool calls ──
            # Add the assistant message with tool calls to conversation
            assistant_msg = {"role": "assistant", "content": content or ""}
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            self.conversation.append(assistant_msg)

            for tc in tool_calls:
                func = tc.get("function", {})
                tool_name = func.get("name", "unknown")
                arguments = func.get("arguments", {})
                tool_call_id = tc.get("id", "")

                # Parse arguments if they're a string
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {}

                # ── Log the action ──
                args_summary = ", ".join(
                    f"{k}={repr(v)[:50]}" for k, v in arguments.items()
                )
                log_act(tool_name, args_summary)

                # ── Execute ──
                result = self.execute_tool(tool_name, arguments)

                # ── Log observation ──
                log_observe(result)

                # Check for task_complete
                if tool_name == "task_complete":
                    final_summary = arguments.get("summary", result)
                    success = arguments.get("success", True)
                    if success:
                        log_result(final_summary)
                    else:
                        log_error(final_summary)

                # Add tool result to conversation
                self.conversation.append({
                    "role": "tool",
                    "content": result,
                })

            # Small delay between iterations to avoid hammering
            time.sleep(0.5)

        if not self.task_done:
            final_summary = "Task reached maximum iterations without completing."
            log_error(final_summary)

        banner("Task Finished", C.GREEN if self.task_done else C.RED)
        print(f"  {final_summary}\n")

        return final_summary


# ─────────────────────────────────────────────────────────────────────────────
# Interactive CLI
# ─────────────────────────────────────────────────────────────────────────────

def print_help():
    print(f"""
{C.CYAN}{C.BOLD}╔══════════════════════════════════════════════════════════════╗
║         🤖 Intelligent Browser Agent — Commands             ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  Just type your request in natural language!                 ║
║                                                              ║
║  Examples:                                                   ║
║    • "Fill my today's timesheet on Tecblic ERP"              ║
║    • "Find the GitHub tab and star the repository"           ║
║    • "Search Google for Python tutorials"                    ║
║    • "Go to the Odoo tab and show me my tasks"               ║
║    • "Click the login button on the active tab"              ║
║                                                              ║
║  Special commands:                                           ║
║    help     — Show this message                              ║
║    tabs     — Quick list of open tabs                        ║
║    quit     — Exit the agent                                 ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝{C.RESET}
""")


def main():
    """Interactive CLI for the intelligent browser agent."""

    print(f"""
{C.CYAN}{C.BOLD}
  ╔══════════════════════════════════════════════════════════════╗
  ║                                                              ║
  ║   🧠  Intelligent Browser Automation Agent                  ║
  ║       with Visual Action Feedback                            ║
  ║                                                              ║
  ║   Powered by {OLLAMA_MODEL} via Ollama               ║
  ║   Connected to Chrome via Tab Tracker Relay                  ║
  ║                                                              ║
  ╚══════════════════════════════════════════════════════════════╝
{C.RESET}""")

    # Check connections
    print(f"  {C.DIM}Checking connections...{C.RESET}")

    # Check relay server
    try:
        resp = requests.get(f"{RELAY_BASE_URL}/health", timeout=3)
        health = resp.json()
        ext_connected = health.get("extension_connected", False)
        print(f"  {C.GREEN}✓{C.RESET} Relay server: {C.GREEN}connected{C.RESET}")
    except Exception:
        print(f"  {C.RED}✗{C.RESET} Relay server: {C.RED}not running{C.RESET}")
        print(f"    {C.DIM}Start it with: python3 relay_server.py{C.RESET}")
        sys.exit(1)

    # Check Chrome extension — wait with retry
    if not ext_connected:
        print(f"  {C.YELLOW}⏳{C.RESET} Chrome extension: {C.YELLOW}waiting for connection...{C.RESET}")
        print(f"    {C.DIM}👉 Click the Chrome extension icon to connect{C.RESET}")
        for i in range(30):
            time.sleep(1)
            try:
                resp = requests.get(f"{RELAY_BASE_URL}/health", timeout=2)
                if resp.json().get("extension_connected", False):
                    ext_connected = True
                    break
            except Exception:
                pass
            spinner = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            print(f"\r    {spinner[i % len(spinner)]} Waiting... ({i+1}s)", end="", flush=True)
        print()

    if ext_connected:
        print(f"  {C.GREEN}✓{C.RESET} Chrome extension: {C.GREEN}connected{C.RESET}")
        print(f"    {C.DIM}Visual feedback will appear on browser pages!{C.RESET}")
    else:
        print(f"  {C.RED}✗{C.RESET} Chrome extension: {C.RED}not connected after 30s{C.RESET}")
        print(f"    {C.YELLOW}⚠  You can still use tab listing, but browser actions will fail.{C.RESET}")
        print(f"    {C.DIM}To fix: Open Chrome → Click the Tab Tracker extension icon{C.RESET}")

    # Check Ollama
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        models = [m["name"] for m in resp.json().get("models", [])]
        if OLLAMA_MODEL in models:
            print(f"  {C.GREEN}✓{C.RESET} Ollama model: {C.GREEN}{OLLAMA_MODEL}{C.RESET}")
        else:
            print(f"  {C.YELLOW}⚠{C.RESET} Model {OLLAMA_MODEL} not found in: {', '.join(models[:5])}")
    except Exception:
        print(f"  {C.RED}✗{C.RESET} Ollama: {C.RED}not reachable{C.RESET}")
        sys.exit(1)

    print(f"""
  {C.CYAN}Visual Feedback:{C.RESET}
    🔴 Red pulsing glow highlights target elements before clicking
    🖱️  Virtual cursor moves to show where the agent is acting
    📋 Toast notifications appear on the page showing actions
    ✅ Green toasts confirm successful actions
""")
    print_help()

    agent = IntelligentBrowserAgent()
    tools = BrowserTools()

    while True:
        try:
            prompt = input(f"{C.GREEN}{C.BOLD}🤖 You > {C.RESET}").strip()
            if not prompt:
                continue

            if prompt.lower() in ("quit", "exit", "q"):
                print(f"\n  {C.DIM}Goodbye! 👋{C.RESET}\n")
                break
            elif prompt.lower() == "help":
                print_help()
                continue
            elif prompt.lower() in ("tabs", "list"):
                print(tools.get_all_tabs())
                continue
            elif prompt.lower() in ("status", "check"):
                connected = tools.check_extension()
                if connected:
                    print(f"  {C.GREEN}✓{C.RESET} Extension is {C.GREEN}connected{C.RESET} — browser actions will work!")
                else:
                    print(f"  {C.RED}✗{C.RESET} Extension is {C.RED}disconnected{C.RESET}")
                    print(f"    {C.DIM}Click the Chrome extension icon to reconnect{C.RESET}")
                continue

            # Pre-flight check: warn if extension is disconnected
            if not tools.check_extension():
                print(f"\n  {C.YELLOW}⚠  Chrome extension is not connected!{C.RESET}")
                print(f"    {C.DIM}Tab listing will work, but clicks/fills/JS won't.{C.RESET}")
                print(f"    {C.DIM}Click the extension icon in Chrome, then try again.{C.RESET}")
                proceed = input(f"    {C.DIM}Continue anyway? (y/n): {C.RESET}").strip().lower()
                if proceed != "y":
                    continue

            # Run the agent
            agent.run_task(prompt)

        except KeyboardInterrupt:
            print(f"\n\n  {C.YELLOW}Interrupted. Type 'quit' to exit or enter a new task.{C.RESET}\n")
        except EOFError:
            print(f"\n  {C.DIM}Goodbye! 👋{C.RESET}\n")
            break
        except Exception as e:
            print(f"\n  {C.RED}Error: {e}{C.RESET}\n")


if __name__ == "__main__":
    main()

