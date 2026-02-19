
import requests
import time
import json
import base64
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime
from .config import RELAY_BASE_URL, OLLAMA_MODEL
import asyncio
from browser_agent.browser_session_adapter import BrowserSession
from browser_agent.dom.service import DomService
from browser_agent.dom.serializer.serializer import DOMTreeSerializer
from browser_agent.dom.views import EnhancedDOMTreeNode

# Global session
_http_session = requests.Session()

# ─────────────────────────────────────────────────────────────────────────────
# Browser Tools (CDP Wrapper)
# ─────────────────────────────────────────────────────────────────────────────

class BrowserTools:
    def __init__(self, base_url: str = RELAY_BASE_URL):
        self.base_url = base_url
        self._overlay_injected = {} # tab_id -> bool
        self.sessions: Dict[int, BrowserSession] = {}
        self.selector_maps: Dict[int, Dict[int, EnhancedDOMTreeNode]] = {}

    def get_active_tab_id(self) -> Optional[int]:
        try:
            resp = _http_session.get(f"{self.base_url}/tabs", timeout=2)
            tabs = resp.json()
            for t in tabs:
                if t.get("active"):
                    return t.get("tab_id")
        except:
            pass
        return None

    def _get_session(self, tab_id: int) -> BrowserSession:
        if tab_id is None:
             tab_id = self.get_active_tab_id()
             if tab_id is None:
                 raise ValueError("tab_id cannot be None and no active tab found")
        
        if tab_id not in self.sessions:
            self.sessions[tab_id] = BrowserSession(self)
        return self.sessions[tab_id]

    async def _get_dom_tree(self, tab_id: int):
        if tab_id is None:
             tab_id = self.get_active_tab_id()
             if tab_id is None:
                 raise ValueError("tab_id cannot be None and no active tab found")
        
        session = self._get_session(tab_id)
        service = DomService(session)
        # Force a fresh state
        return await service.get_dom_tree(target_id=tab_id)

    def check_extension(self) -> bool:
        """Check if extension is connected via relay."""
        try:
            resp = _http_session.get(f"{self.base_url}/health", timeout=1)
            return resp.json().get("extension_connected", False)
        except Exception:
            return False

    def _cdp(self, tab_id: int, method: str, params: Optional[Dict] = None) -> Dict:
        """Execute a raw CDP command via relay."""
        if tab_id is None:
             tab_id = self.get_active_tab_id()
             if tab_id is None:
                 return {"error": "No active tab found"}
        payload = {
            "method": method,
            "params": params or {}
        }
        # Relay server expects POST /cdp/{tab_id}
        resp = _http_session.post(f"{self.base_url}/cdp/{tab_id}", json=payload, timeout=10)
        return resp.json()

    def _eval_js(self, tab_id: int, script: str) -> Any:
        """Evaluate JavaScript in the given tab."""
        result = self._cdp(tab_id, "Runtime.evaluate", {
            "expression": script,
            "returnByValue": True,
            "awaitPromise": True
        })
        # Check for exception details
        if "exceptionDetails" in result:
             # Try to extract the actual error message
             exc = result["exceptionDetails"]
             text = exc.get("text", "JS Error")
             exc_val = exc.get("exception", {}).get("description", "")
             return f"Error: {text} - {exc_val}"
             
        if "result" not in result:
             return f"Error: No result from JS eval: {result}"
             
        return result["result"].get("result", {}).get("value")

    def _inject_overlay(self, tab_id: int):
        """Inject visual overlay (cursor, toasts, highlights) into the tab."""
        if self._overlay_injected.get(tab_id):
            return

        js = r"""
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
                .__agent_highlight {
                    outline: 3px solid #ff0055 !important;
                    outline-offset: 2px !important;
                    animation: __agent_pulse 0.6s ease-out 2 !important;
                    transition: outline 0.3s ease !important;
                    position: relative !important;
                    z-index: 2147483646 !important;
                }
                #__agent_toast_container {
                    position: fixed;
                    top: 20px;
                    right: 20px;
                    z-index: 2147483647;
                    display: flex;
                    flex-direction: column;
                    gap: 8px;
                    pointer-events: none;
                    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
                }
                .__agent_toast {
                    background: rgba(15, 23, 42, 0.95);
                    color: white;
                    padding: 12px 20px;
                    border-radius: 8px;
                    font-size: 14px;
                    line-height: 1.4;
                    max-width: 400px;
                    border-left: 4px solid #3b82f6;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
                    border: 1px solid rgba(255,255,255,0.1);
                    animation: __agent_fadeIn 0.3s ease-out forwards;
                    display: flex;
                    align-items: center;
                    gap: 8px;
                }
                .__agent_toast.success { border-left-color: #10b981; }
                .__agent_toast.error { border-left-color: #ef4444; }
                .__agent_toast.info { border-left-color: #3b82f6; }
                
                #__agent_cursor {
                    position: fixed;
                    width: 24px;
                    height: 24px;
                    z-index: 2147483647;
                    pointer-events: none;
                    transition: left 0.5s cubic-bezier(0.25, 1, 0.5, 1), top 0.5s cubic-bezier(0.25, 1, 0.5, 1);
                    filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3));
                }
                #__agent_cursor_label {
                    position: absolute;
                    left: 24px;
                    top: 18px;
                    background: #0f172a;
                    color: #fff;
                    font-size: 11px;
                    padding: 4px 8px;
                    border-radius: 4px;
                    white-space: nowrap;
                    font-weight: 600;
                    border: 1px solid rgba(255,255,255,0.2);
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
            // Simple cursor SVG
            cursor.innerHTML = `
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M5.65376 12.3673H5.46026L5.31717 12.4976L0.500002 16.8829L0.500002 1.19177L23.0212 12.3673H5.65376Z" fill="#3b82f6" stroke="white" stroke-width="1.5"/>
                </svg>
                <span id="__agent_cursor_label">🤖 Agent</span>
            `;
            cursor.style.display = 'none';
            document.body.appendChild(cursor);

            // --- Global API ---
            window.__agentShowToast = function(msg, type, duration) {
                var container = document.getElementById('__agent_toast_container');
                if (!container) return;
                
                var toast = document.createElement('div');
                toast.className = '__agent_toast ' + (type || 'info');
                toast.innerHTML = msg;
                
                container.appendChild(toast);
                
                // Auto remove
                setTimeout(function() {
                    toast.style.animation = '__agent_fadeOut 0.3s ease-in forwards';
                    setTimeout(function() { toast.remove(); }, 300);
                }, duration || 3000);
            };

            window.__agentHighlight = function(selector, label) {
                var el;
                // Check if XPath
                if (selector.startsWith('//') || selector.startsWith('(') || selector.startsWith('/HTML')) {
                    try {
                        var res = document.evaluate(selector, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                        el = res.singleNodeValue;
                    } catch(e) {}
                } else {
                    try { el = document.querySelector(selector); } catch(e) {}
                }
                
                if (!el) return false;
                
                // Scroll to view
                el.scrollIntoView({ block: 'center', behavior: 'smooth' });
                el.classList.add('__agent_highlight');

                // Move cursor to element
                var rect = el.getBoundingClientRect();
                var cur = document.getElementById('__agent_cursor');
                if (cur) {
                    cur.style.display = 'block';
                    cur.style.left = (rect.left + rect.width / 2) + 'px';
                    cur.style.top = (rect.top + rect.height / 2) + 'px';
                    
                    var labelEl = document.getElementById('__agent_cursor_label');
                    if (labelEl) labelEl.textContent = label || 'Acting...';
                }

                // Remove highlight after animation
                setTimeout(function() {
                    el.classList.remove('__agent_highlight');
                }, 2000);
                return true;
            };

            window.__agentMoveCursor = function(x, y, label) {
                var cur = document.getElementById('__agent_cursor');
                if (cur) {
                    cur.style.display = 'block';
                    cur.style.left = x + 'px';
                    cur.style.top = y + 'px';
                    
                    var labelEl = document.getElementById('__agent_cursor_label');
                    if (labelEl) labelEl.textContent = label || 'Move';
                }
            };

            return 'Visual overlay injected successfully';
        })()
        """
        self._eval_js(tab_id, js)
        self._overlay_injected[tab_id] = True

    def _show_toast(self, tab_id: int, message: str, type: str = "info", duration: int = 3000):
        """Show a visual toast notification on the page."""
        safe_msg = message.replace("'", "\\'").replace("\n", " ")
        self._eval_js(tab_id, f"window.__agentShowToast && window.__agentShowToast('{safe_msg}', '{type}', {duration})")

    def _highlight_element(self, tab_id: int, selector: str, action_type: str = "Interact"):
        """Highlight an element with a glow and move the cursor to it."""
        safe_sel = selector.replace("'", "\\'")
        safe_label = action_type.replace("'", "\\'")
        self._eval_js(tab_id, f"window.__agentHighlight && window.__agentHighlight('{safe_sel}', '{safe_label}')")

    def get_all_tabs(self) -> str:
        try:
            resp = _http_session.get(f"{self.base_url}/tabs", timeout=3)
            tabs = resp.json()
            if not tabs:
                # User request: auto-open a tab if none found
                self.open_new_tab("https://www.google.com")
                time.sleep(1.0) # wait for collection
                return "No tabs found. I've opened a new Google tab for you. Please call get_all_tabs again to see it."
            
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
            error_msg = f"Error: {e}"
            try:
                # Try to append minimal response info if available
                if 'resp' in locals():
                    error_msg += f" (Status: {resp.status_code}, Text: {resp.text[:100]})"
            except:
                pass
            return error_msg

    def search_tabs(self, query: str) -> str:
        try:
            resp = _http_session.get(f"{self.base_url}/tabs", timeout=3)
            tabs = resp.json()
            matches = []
            for t in tabs:
                if query.lower() in t.get("title", "").lower() or query.lower() in t.get("url", "").lower():
                    matches.append(t)
            
            if not matches:
                return f"No tabs found matching '{query}'"
            
            lines = [f"Found {len(matches)} matching tabs:\n"]
            for t in matches:
                active = "🟢 " if t.get("active") else "⚪ "
                lines.append(
                    f"- {active}{t.get('title')}\n"
                    f"  ID: {t.get('tab_id')}\n"
                    f"  URL: {t.get('url')}\n"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    def get_page_info(self, tab_id: int) -> str:
        js = "({url: window.location.href, title: document.title, readyState: document.readyState})"
        result = self._eval_js(tab_id, js)
        if isinstance(result, dict):
            return (
                f"Title: {result.get('title')}\n"
                f"URL: {result.get('url')}\n"
                f"State: {result.get('readyState')}"
            )
        return str(result)

    def get_visible_text(self, tab_id: int) -> str:
        js = """
        (function() {
            var body = document.body;
            if (!body) return '';
            
            // Use a TreeWalker to get text nodes
            var walker = document.createTreeWalker(
                body,
                NodeFilter.SHOW_TEXT,
                {
                    acceptNode: function(node) {
                        if (!node.textContent.trim()) return NodeFilter.FILTER_SKIP;
                        if (node.parentElement && (
                            node.parentElement.tagName === 'SCRIPT' || 
                            node.parentElement.tagName === 'STYLE' || 
                            node.parentElement.tagName === 'NOSCRIPT' ||
                            getComputedStyle(node.parentElement).display === 'none' ||
                            getComputedStyle(node.parentElement).visibility === 'hidden'
                        )) return NodeFilter.FILTER_REJECT;
                        return NodeFilter.FILTER_ACCEPT;
                    }
                },
                false
            );

            var text = [];
            while(walker.nextNode()) {
                text.push(walker.currentNode.textContent.trim());
            }
            return text.join('\\n');
        })()
        """
        result = self._eval_js(tab_id, js)
        if isinstance(result, str):
            # Truncate
            if len(result) > 4000:
                result = result[:4000] + "\n... (truncated)"
            return result
        return str(result)

    def _get_dom_fingerprint(self, tab_id: int) -> str:
        """Get a simple fingerprint of the current page state (URL + interactive element hash)."""
        js = """
        (function() {
            var url = window.location.href;
            try {
                var elements = document.querySelectorAll('button, a, input, select, textarea');
                var sig = "";
                // Hash top 20 elements
                for(var i=0; i<Math.min(elements.length, 20); i++) {
                    var el = elements[i];
                    sig += el.tagName + (el.id||"") + (el.name||"") + (el.className||"").substring(0,10);
                }
                return url + "::" + elements.length + "::" + sig.length + "::" + sig.substring(0, 50);
            } catch(e) { return url + "::error"; }
        })()
        """
        return str(self._eval_js(tab_id, js))

    def get_page_interactive_elements(self, tab_id: int) -> str:
        """Get a list of interactive elements using DomService."""
        try:
            dom_result = asyncio.run(self._get_dom_tree(tab_id)) # detect_js_listeners defaults to False now
            tree = dom_result[0]
            serializer = DOMTreeSerializer(tree)
            result, timing = serializer.serialize_accessible_elements()
            
            # Cache the selector map for this tab
            self.selector_maps[tab_id] = result.selector_map
            
            lines = [f"Found {len(result.selector_map)} interactive elements:\n"]
            
            def traverse(node, depth=0):
                if node.is_interactive:
                     # Find index in selector_map
                     idx = -1
                     for k, v in result.selector_map.items():
                         if v.backend_node_id == node.original_node.backend_node_id:
                             idx = k
                             break
                     if idx != -1:
                        # Build string representation
                        tag = node.original_node.tag_name
                        text = node.original_node.get_meaningful_text_for_llm()[:60]
                        # attributes to show
                        attrs = node.original_node.attributes or {}
                        
                        extra = ""
                        if 'href' in attrs: extra += f" href=\"{attrs['href'][:40]}\""
                        if 'name' in attrs: extra += f" name=\"{attrs['name']}\""
                        if 'placeholder' in attrs: extra += f" placeholder=\"{attrs['placeholder']}\""
                        if 'aria-label' in attrs: extra += f" aria-label=\"{attrs['aria-label']}\""
                        if 'role' in attrs: extra += f" role=\"{attrs['role']}\""
                        if 'type' in attrs: extra += f" type=\"{attrs['type']}\""
                        
                        indent = "  " * depth
                        lines.append(f"{indent}[{idx}] <{tag}>{text}</{tag}>{extra}")
                
                for child in node.children:
                    traverse(child, depth + 1)

            if result._root:
                traverse(result._root)
            
            return "\n".join(lines)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return f"Error analyzing DOM: {e}"

    def click_element(self, tab_id: int, selector: str) -> str:
        """Click an element systematically. Supports CSS selector or Index from get_page_interactive_elements."""
        try:
            target_node_id = None
            xpath = None
            
            # Check if selector is an index
            if selector.isdigit() or (selector.startswith("[") and selector.endswith("]")):
                idx = int(selector.strip("[]"))
                if tab_id in self.selector_maps and idx in self.selector_maps[tab_id]:
                    node = self.selector_maps[tab_id][idx]
                    target_node_id = node.backend_node_id
                    # Try to get xpath for visual feedback
                    if hasattr(node, 'xpath'):
                        xpath = node.xpath
                    print(f"DEBUG: Resolved index {idx} to backend_node_id {target_node_id}")
            
            # 1. Capture pre-action state
            pre_fingerprint = self._get_dom_fingerprint(tab_id)
            pre_url = pre_fingerprint.split("::")[0] if "::" in pre_fingerprint else ""
            
            self._inject_overlay(tab_id)
            self._show_toast(tab_id, f'Clicking: <b>{selector[:60]}</b>', 'action')
            
            # Visual feedback: Highlight using xpath if available (for index), else selector
            highlight_selector = xpath if xpath else selector
            # Avoid highlighting if it's a raw index without xpath (would fail)
            if not (highlight_selector.isdigit() or (highlight_selector.startswith("[") and highlight_selector.endswith("]"))):
                self._highlight_element(tab_id, highlight_selector, 'click')
            
            # If we have a backend node ID, try to click it robustly via CDP
            success = False
            if target_node_id:
                try:
                    # Resolve node to object
                    res = self._cdp(tab_id, "DOM.resolveNode", {"backendNodeId": target_node_id})
                    if "object" in res.get("result", {}):
                        obj_id = res["result"]["object"]["objectId"]
                        # Scroll and click
                        # We use Runtime.callFunctionOn
                        js_click = """
                        function() { 
                            this.scrollIntoView({block: 'center', inline: 'center'});
                            this.focus();
                            this.click(); 
                            return 'clicked_via_cdp';
                        }
                        """
                        click_res = self._cdp(tab_id, "Runtime.callFunctionOn", {
                            "objectId": obj_id,
                            "functionDeclaration": js_click,
                            "returnByValue": True
                        })
                        if not click_res.get("result", {}).get("exceptionDetails"):
                            success = True
                except Exception as e:
                    print(f"CDP click failed: {e}, falling back to JS selector")

            if not success:
               # Fallback to selector-based click (original logic)
               # Only works if selector is NOT an index (since we likely failed index resolution or CDP click)
               if highlight_selector == selector:
                   # Only highlight if not already done
                   pass 
               
               escaped = selector.replace("'", "\\'").replace("\\", "\\\\")
               js = f"""
               (function() {{
                   var el = document.querySelector('{escaped}');
                   if (!el) {{
                       // Try case-insensitive text match if simple selector fails
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
                       el.classList.add('__agent_highlight');
                       el.click();
                       setTimeout(function() {{ el.classList.remove('__agent_highlight'); }}, 2000);
                       return 'clicked';
                   }}
                   return 'not_found';
               }})()
               """
               result = self._eval_js(tab_id, js)
               if result == "not_found":
                   return f"Error: Element not found: {selector}"

            # 2. Post-action verification
            time.sleep(0.5) # Wait for page reaction
            
            post_fingerprint = self._get_dom_fingerprint(tab_id)
            post_url = post_fingerprint.split("::")[0] if "::" in post_fingerprint else ""

            # 3. Generate grounded feedback
            feedback = f"Clicked element '{selector}'."
            
            # URL changed?
            if pre_url and post_url and pre_url != post_url:
                feedback += f" URL changed ...{pre_url[-20:]} -> ...{post_url[-20:]}."
            # DOM changed?
            elif pre_fingerprint != post_fingerprint:
                # Basic diff
                feedback += " Page content updated (DOM changed)."
            else:
                feedback += " No obvious page change detected (might be subtle or require visual check)."

            return feedback
        except Exception as e:
            return f"Error clicking element: {e}"

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
                return 'not_found';
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

            setTimeout(function() {{ el.classList.remove('__agent_highlight'); }}, 2000);
            return 'filled';
        }})()
        """
        result = self._eval_js(tab_id, js)
        
        if result == "not_found":
             return f"Error: Input not found: {selector}"

        # Get value to verify
        val = self._eval_js(tab_id, f"document.querySelector('{escaped_sel}').value")
        return f"Filled input '{selector}' with: '{text}'. Current value verified as: '{val}'"

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
            resp = _http_session.post(f"{self.base_url}/collect", timeout=3)
            return "Collection triggered! Tab list will be refreshed in a moment."
        except Exception as e:
            return f"Error: {e}"

    def open_new_tab(self, url: str) -> str:
        """Open a new tab in Chrome."""
        try:
            # Use the new /open-tab endpoint
            resp = _http_session.post(
                f"{self.base_url}/open-tab",
                json={"url": url},
                timeout=5
            )
            try:
                result = resp.json()
            except:
                return f"Opened new tab: {url} (Warning: invalid JSON response: {resp.text})"

            # Check for success
            # The extension usually returns the Tab object or {result: Tab}
            # If relay wraps it, check structure.
            # Assuming result is what send_request_to_extension returns.
            
            # If success, try to find ID
            tab_id = result.get("id") or result.get("tabId") or result.get("result", {}).get("id")
            
            if tab_id:
                # Trigger collection for good measure
                self.trigger_collection()
                return f"Opened new tab: {url} (ID: {tab_id})"
            
            # Fallback if no ID found but successful
            self.trigger_collection()
            return f"Opened new tab: {url}"

        except Exception as e:
            return f"Error opening tab: {e}"

    def switch_tab(self, tab_id: int) -> str:
        """
        Switch to an existing tab by its ID.
        """
        try:
            resp = _http_session.post(f"{self.base_url}/activate-tab/{tab_id}", timeout=5)
            if resp.status_code == 200:
                # print(f"Switched to tab {tab_id}")
                return f"Switched to tab {tab_id}"
            else:
                return f"Failed to switch tab: {resp.text}"
        except Exception as e:
            return f"Error switching tab: {e}"

    def take_screenshot(self, tab_id: int) -> dict:
        """Take a screenshot using CDP Page.captureScreenshot."""
        self._inject_overlay(tab_id)
        self._show_toast(tab_id, "📸 Taking screenshot...", "info", 2000)
        try:
            result = self._cdp(tab_id, "Page.captureScreenshot", {
                "format": "png",
                "quality": 80,
            })
            if isinstance(result, dict):
                data = result.get("result", {})
                if isinstance(data, dict) and data.get("data"):
                    return {"base64": data["data"], "success": True}
                if result.get("data"):
                    return {"base64": result["data"], "success": True}
            return {"error": "No screenshot data returned", "success": False}
        except Exception as e:
            return {"error": str(e), "success": False}

    def click_at_coordinates(self, tab_id: int, x: int, y: int) -> str:
        """Click at exact (x, y) pixel coordinates using CDP Input.dispatchMouseEvent."""
        self._inject_overlay(tab_id)
        
        # Visual feedback: Move cursor to point
        self._eval_js(tab_id, f"window.__agentMoveCursor && window.__agentMoveCursor({x}, {y}, 'Click ({x},{y})')")
        self._show_toast(tab_id, f'Clicking at ({x}, {y})', 'action')
        
        # Brief wait for cursor to arrive
        time.sleep(0.3)

        try:
            # Mouse down
            self._cdp(tab_id, "Input.dispatchMouseEvent", {
                "type": "mousePressed",
                "x": x,
                "y": y,
                "button": "left",
                "clickCount": 1,
            })
            # Mouse up
            self._cdp(tab_id, "Input.dispatchMouseEvent", {
                "type": "mouseReleased",
                "x": x,
                "y": y,
                "button": "left",
                "clickCount": 1,
            })

            # Try to identify what was clicked for feedback
            identify_js = f"""
            (function() {{
                var el = document.elementFromPoint({x}, {y});
                if (!el) return 'Clicked at ({x}, {y}) - no element found';
                var tag = el.tagName.toLowerCase();
                var text = (el.textContent || '').trim().substring(0, 50);
                var desc = '<' + tag + '>';
                if (el.id) desc += ' #' + el.id;
                if (text) desc += ' "' + text + '"';
                return 'Clicked at ({x}, {y}) on ' + desc;
            }})()
            """
            result = self._eval_js(tab_id, identify_js)
            self._show_toast(tab_id, f'✅ {result}', 'success', 2000)
            return str(result)
        except Exception as e:
            return f"Click at ({x}, {y}) failed: {e}"

    def task_complete(self, summary: str, success: bool) -> str:
        return f"{'✅' if success else '❌'} TASK {'COMPLETE' if success else 'FAILED'}: {summary}"


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
        "open_new_tab": lambda **kw: tools.open_new_tab(kw["url"]),
        "click_at_coordinates": lambda **kw: tools.click_at_coordinates(kw["tab_id"], kw["x"], kw["y"]),
        "take_screenshot": lambda **kw: tools.take_screenshot(kw["tab_id"]),
        "task_complete": lambda **kw: tools.task_complete(
            kw["summary"], kw.get("success", True)
        ),
        "switch_tab": lambda **kw: tools.switch_tab(kw["tab_id"]),
    }


def build_system_prompt() -> str:
    now = datetime.now()
    return f"""You are an intelligent browser automation agent with VISION. You control the user's Chrome browser to accomplish tasks they describe in natural language.

YOU CAN SEE SCREENSHOTS of the browser. After key actions, a screenshot is automatically taken and shown to you. You can also call take_screenshot at any time to see the current page.

## Current Context
- **Date**: {now.strftime('%A, %B %d, %Y')}
- **Time**: {now.strftime('%I:%M %p')}
- **Timezone**: IST (India Standard Time)

## Understanding User Intent
- The user may use informal language, typos, or abbreviations
- "Tecblic" / "tecblic" = the user's company (Tecblic Private Limited)
- "timesheet" = daily time tracking form, likely on Odoo ERP (internalerp.tecblic.com)
- "fill timesheet" = enter working hours for today
- **Interpret the user's intent, don't ask for clarification — just do it.**

## Your Capabilities
You have access to browser control tools that let you:
1. **See** — Take screenshots, list tabs, read page content, inspect interactive elements (with index-based selection)
2. **Navigate** — Open URLs, open new tabs, switch between tabs
3. **Interact** — Click buttons/links (by selector OR by coordinates), fill forms, scroll pages
4. **Execute** — Run arbitrary JavaScript for advanced interactions

## How to Work (ReAct Pattern with Vision)
For each step:
1. **Observe** — Look at the screenshot to understand the current page state.
2. **Analysis** — What is on the page? Does it match what I expected?
3. **Plan** — specific, short-term plan for the NEXT few steps.
   - Example: "I see the search bar. I will click it, type query, and press Enter."
   - Example: "The tab is already open. I will switch to tab 42."
4. **Action** — Call the appropriate tool.

**IMPORTANT**: You must output your thinking/plan in the response BEFORE calling the tool.

## Important Rules
1. **Always start by observing** — Use get_all_tabs to see what's open. If the needed tab is open, switch to it. If not, open a new tab.
2. **Be precise with selectors** — Use get_page_interactive_elements to find elements. You can click using the `[index]` from the list (e.g. `[42]`).
3. **Wait after navigation** — After clicking links or navigating, use wait_for_page_load before inspecting the new page.
4. **Handle errors gracefully** — If a selector doesn't work, try alternative approaches (different selector, JS execution, or click_at_coordinates).
5. **Fill forms completely** — When filling forms (like timesheets), fill ALL required fields.
6. **Verify your actions** — After important actions, read the page or take a screenshot to verify they succeeded.
7. **Call task_complete** when done — Always end by calling task_complete with a summary.

## Tips for Odoo/ERP Timesheets
- The Odoo timesheet URL is typically: internalerp.tecblic.com
- Look for "Timesheet" or similar menu items.
- Timesheet forms usually have: Date, Description/Activity, Project, Hours fields.
- Today's date should be pre-filled or auto-selected.
- Standard work hours: 8 hours if not specified.
- Fields often use specific classes like `.o_field_widget` or `.o_input`.
- After filling, look for a Save button/icon and click it.

## Tips for Form Interaction
- For date pickers, try clicking them and using JS to set the value.
- For dropdowns/selects, use click to open + then select the option.
- If standard clicks fail, use `execute_javascript` or `click_at_coordinates`.
"""

