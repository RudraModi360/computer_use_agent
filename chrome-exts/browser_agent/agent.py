
import time
import sys
import json
from typing import Dict, List, Optional
from datetime import datetime

from .config import (
    MAX_ITERATIONS,
    MAX_CONVERSATION_MESSAGES,
    TOOL_DEFINITIONS,
    OLLAMA_MODEL
)
from .telemetry import TokenTelemetry, C
from .llm_client import OllamaChat, parse_tool_calls_from_text
from .browser_tools import BrowserTools, build_tool_router, build_system_prompt

# ─────────────────────────────────────────────────────────────────────────────
# Utils: Logging
# ─────────────────────────────────────────────────────────────────────────────

def log_iter(current, total):
    print(f"\n{C.BLUE}{C.BOLD}🔄 Step {current}/{total}{C.RESET}")

def log_act(tool_name, args_summary):
    print(f"  {C.YELLOW}🛠️  Action:{C.RESET} {C.BOLD}{tool_name}{C.RESET} ({args_summary})")

def log_observe(result):
    clean_res = result.replace("\n", " ")[:150]
    print(f"  {C.CYAN}👀 Observe:{C.RESET} {clean_res}...")

def log_result(text):
    print(f"\n{C.GREEN}{C.BOLD}🏁 Result:{C.RESET} {text}")

def log_error(text):
    print(f"\n{C.RED}{C.BOLD}❌ Error:{C.RESET} {text}")

def banner(text, color=C.BLUE):
    print(f"\n{color}{C.BOLD}╔{'═'*(len(text)+4)}╗")
    print(f"║  {text}  ║")
    print(f"╚{'═'*(len(text)+4)}╝{C.RESET}")


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
        self.telemetry = TokenTelemetry()
        self._pending_screenshot: Optional[str] = None  # base64 screenshot for next LLM call
        # Tools that change what's visible — auto-screenshot after these
        self._visual_tools = {
            "click_element", "click_at_coordinates", "fill_input",
            "navigate_to_url", "scroll_page", "open_new_tab",
        }
        # Tools that operate on a tab — auto-focus before these
        self._tab_tools = {
            "click_element", "click_at_coordinates", "fill_input",
            "navigate_to_url", "scroll_page", "get_page_info",
            "get_page_interactive_elements", "get_visible_text",
            "execute_javascript", "take_screenshot",
        }

    def reset(self):
        """Reset state for a new task."""
        self.conversation = [{"role": "system", "content": build_system_prompt()}]
        self.task_done = False
        self._pending_screenshot = None

    def _trim_conversation(self):
        """Trim conversation to prevent token bloat.
        
        Keeps: system prompt + last N messages.
        Also truncates old tool outputs to save tokens.
        """
        if len(self.conversation) > MAX_CONVERSATION_MESSAGES:
            # Keep system prompt (first message) + last (MAX-1) messages
            system = self.conversation[0]
            recent = self.conversation[-(MAX_CONVERSATION_MESSAGES - 1):]
            self.conversation = [system] + recent

        # Compress old tool outputs (keep only the last 3 full outputs)
        # We target DOM dumps specifically as they are the largest token hogs
        tool_outputs_kept = 0
        for i in range(len(self.conversation) - 1, 0, -1):
            msg = self.conversation[i]
            if msg.get("role") == "tool":
                tool_outputs_kept += 1
                if tool_outputs_kept > 3:
                    content = msg.get("content", "")
                    # Aggressive summarization for old DOM dumps
                    if "Found" in content and "interactive elements" in content:
                        lines = content.splitlines()
                        if len(lines) > 5:
                            msg["content"] = f"(History: {lines[0]} - details hidden)"
                    # General truncation for other long outputs
                    elif len(content) > 300:
                         msg["content"] = f"(History: Output truncated, length {len(content)}. Summary: {content[:150]}...)"

    def _focus_tab(self, tab_id: int):
        """Bring Chrome to foreground and switch to the given tab."""
        # This requires relay endpoint... handled by browser tools?
        # Actually in intelligent_agent.py it was calling _http_session directly.
        # We can implement this on BrowserTools, or just copy the logic here using BrowserTools' session?
        # Better: Add activate_tab to BrowserTools.
        # But for now, to keep it simple, I'll use the browser tool's base_url + requests.
        # Wait, BrowserTools has `_http_session`. I shouldn't access private members.
        # But `activate_tab` is not in `BrowserTools` public API yet?
        # I'll use `requests.post` directly since it's a side effect.
        try:
            from .browser_tools import _http_session, RELAY_BASE_URL
            _http_session.post(
                f"{RELAY_BASE_URL}/activate-tab/{tab_id}",
                timeout=2,
            )
        except Exception:
            pass  # Best-effort, don't fail the action

    def execute_tool(self, name: str, arguments: Dict) -> str:
        """Execute a tool by name with given arguments and return result."""
        if name == "task_complete":
            self.task_done = True

        fn = self.tool_router.get(name)
        if fn is None:
            return f"Unknown tool: {name}"

        # Coerce tab_id to int if present (fixes scientific notation floats from LLM)
        if "tab_id" in arguments:
            try:
                # Convert to float first to handle '4.9e8', then to int
                arguments["tab_id"] = int(float(str(arguments["tab_id"])))
            except (ValueError, TypeError):
                pass

        # Auto-focus tab before any tab-based action
        if name in self._tab_tools:
            tab_id = arguments.get("tab_id")
            if tab_id:
                self._focus_tab(tab_id)

        try:
            result = fn(**arguments)
            
            # Handle take_screenshot specially — store image for VLM
            if name == "take_screenshot":
                if isinstance(result, dict) and result.get("success"):
                    self._pending_screenshot = result["base64"]
                    return "Screenshot taken — I can now see the page."
                else:
                    error = result.get("error", "Unknown error") if isinstance(result, dict) else str(result)
                    return f"Screenshot failed: {error}"

            # Auto-screenshot after visual actions
            if name in self._visual_tools and not self.task_done:
                try:
                    tab_id = arguments.get("tab_id")
                    if tab_id:
                        time.sleep(0.3)  # Brief wait for page to update
                        ss = self.browser.take_screenshot(tab_id)
                        if isinstance(ss, dict) and ss.get("success"):
                            self._pending_screenshot = ss["base64"]
                except Exception:
                    pass  # Don't fail the action if screenshot fails

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

        # Inject current tabs into history so the agent knows what's open
        try:
            tabs_list = self.browser.get_all_tabs()
            self.conversation.append({
                "role": "system", 
                "content": f"## Current Tabs\n{tabs_list}\n\n(Use existing tabs if possible!)"
            })
        except Exception as e:
            print(f"{C.RED}Warning: Could not fetch initial tabs: {e}{C.RESET}")

        # Add user message
        self.conversation.append({"role": "user", "content": user_prompt})

        final_summary = ""
        text_only_rounds = 0   # Track consecutive text-only (no tool) rounds

        for iteration in range(1, MAX_ITERATIONS + 1):
            if self.task_done:
                break

            log_iter(iteration, MAX_ITERATIONS)

            # ── Ask LLM (trim first to keep it fast) ──
            self._trim_conversation()
            
            # Include pending screenshot if available
            images_for_llm = None
            if self._pending_screenshot:
                images_for_llm = [self._pending_screenshot]
                self._pending_screenshot = None  # Clear after use
            
            try:
                t0 = time.perf_counter()
                response = self.llm.chat(
                    messages=self.conversation,
                    tools=TOOL_DEFINITIONS,
                    images=images_for_llm,
                    stream_to_terminal=True,
                )
                elapsed = time.perf_counter() - t0
                has_img = bool(images_for_llm)

                # Extract token counts for telemetry
                input_tokens = response.pop("_input_tokens", 0)
                output_tokens = response.pop("_output_tokens", 0)
                self.telemetry.record(input_tokens, output_tokens, elapsed)
                print(f"  {self.telemetry.step_summary(input_tokens, output_tokens, elapsed, has_img)}")

            except Exception as e:
                log_error(f"LLM request failed: {e}")
                time.sleep(2)
                continue

            # Extract thinking (chain of thought) — already printed during streaming
            thinking = response.get("thinking", "")
            content = response.get("content", "")
            tool_calls = response.get("tool_calls") or []

            # If no native tool calls, try parsing ACTION: blocks from text
            if not tool_calls and content:
                tool_calls = parse_tool_calls_from_text(content)

            # Thinking already streamed, skip separate log

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

        if not self.task_done:
            final_summary = "Task reached maximum iterations without completing."
            log_error(final_summary)

        banner("Task Finished", C.GREEN if self.task_done else C.RED)
        print(f"  {final_summary}\n")
        print(self.telemetry.session_summary())
        print()

        return final_summary
