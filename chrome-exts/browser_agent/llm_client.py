
import json
import sys
import re
from typing import List, Dict, Optional, Any
import ollama
from .config import OLLAMA_MODEL, OLLAMA_FALLBACK_MODEL
from .telemetry import C

# ─────────────────────────────────────────────────────────────────────────────
# LLM Client (Ollama)
# ─────────────────────────────────────────────────────────────────────────────

class OllamaChat:
    def __init__(self, model: str = OLLAMA_MODEL):
        self.model = model
        self.client = ollama.Client()
        self._supports_native_tools = {} # cache per model

    def chat(self, messages: List[Dict], tools: List[Dict] = None, images: List[str] = None, stream_to_terminal: bool = False) -> Dict:
        """
        Send chat request to Ollama with robustness fallback.
        """
        # Create a copy so we don't mutate original history
        msg_copy = [m.copy() for m in messages]

        # Attach images to the last user message if present
        if images and msg_copy:
            last_msg = msg_copy[-1]
            if last_msg.get("role") == "user":
                last_msg["images"] = images

        # Models to try in order
        models = [self.model]
        if OLLAMA_FALLBACK_MODEL and OLLAMA_FALLBACK_MODEL != self.model:
            models.append(OLLAMA_FALLBACK_MODEL)

        last_exception = None

        for model_name in models:
            try:
                # Check native tool support cache for this model
                supports_tools = self._supports_native_tools.get(model_name, None)
                
                # Try native tools if we think it's supported or haven't checked
                if tools and supports_tools is not False:
                    try:
                        response = self.client.chat(
                            model=model_name,
                            messages=msg_copy,
                            stream=False,
                            tools=tools,
                            options={"temperature": 0.2, "num_predict": 2048},
                        )
                        self._supports_native_tools[model_name] = True
                        result = self._extract_message(response)
                        result["_input_tokens"] = getattr(response, "prompt_eval_count", 0) or 0
                        result["_output_tokens"] = getattr(response, "eval_count", 0) or 0
                        return result
                    except Exception as e:
                        # If 400 Bad Request, likely tools not supported
                        if "400" in str(e) or "Bad Request" in str(e):
                            self._supports_native_tools[model_name] = False
                        else:
                            raise e

                # Fallback to streaming/standard chat (no native tools or tools failed)
                if stream_to_terminal:
                    return self._stream_chat(msg_copy, model_name, tools)
                else:
                    response = self.client.chat(
                        model=model_name,
                        messages=msg_copy,
                        stream=False,
                        options={"temperature": 0.2, "num_predict": 2048},
                    )
                    result = self._extract_message(response)
                    result["_input_tokens"] = getattr(response, "prompt_eval_count", 0) or 0
                    result["_output_tokens"] = getattr(response, "eval_count", 0) or 0
                    return result

            except Exception as e:
                last_exception = e
                print(f"\n  {C.YELLOW}⚠️ Model '{model_name}' failed: {e}. Switching to fallback...{C.RESET}")
                continue

        raise last_exception or Exception("All models failed.")

    def _stream_chat(self, messages: List[Dict], model_name: str, tools: List[Dict] = None) -> Dict:
        """Stream chat response, printing tokens to terminal as they arrive."""
        print(f"  {C.DIM}(Using model: {model_name}){C.RESET}")
        content_parts = []
        thinking_parts = []
        tool_calls = None
        input_tokens = 0
        output_tokens = 0
        is_thinking = False
        printed_prefix = False
        
        stream = self.client.chat(
            model=model_name,
            messages=messages,
            stream=True,
            options={"temperature": 0.2, "num_predict": 2048},
        )

        for chunk in stream:
            msg = chunk.get("message", {})
            delta = ""
            if hasattr(msg, "content"):
                delta = msg.content or ""
            elif isinstance(msg, dict):
                delta = msg.get("content", "")

            # Check for thinking tokens
            thinking_delta = ""
            if hasattr(msg, "thinking"):
                thinking_delta = msg.thinking or ""
            elif isinstance(msg, dict):
                thinking_delta = msg.get("thinking", "")

            if thinking_delta:
                if not is_thinking:
                    is_thinking = True
                    sys.stdout.write(f"  {C.MAGENTA}🧠 Think:{C.RESET} {C.DIM}")
                    sys.stdout.flush()
                thinking_parts.append(thinking_delta)
                # Print thinking tokens dimmed
                sys.stdout.write(thinking_delta)
                sys.stdout.flush()

            if delta:
                if is_thinking:
                    is_thinking = False
                    sys.stdout.write(f"{C.RESET}\n")
                    sys.stdout.flush()
                if not printed_prefix:
                    printed_prefix = True
                    sys.stdout.write(f"  {C.WHITE}💬 Agent:{C.RESET} {C.DIM}")
                    sys.stdout.flush()
                content_parts.append(delta)
                sys.stdout.write(delta)
                sys.stdout.flush()

            # Check for tool calls in streaming
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                tool_calls = msg.tool_calls

            # Final chunk has token counts
            if chunk.get("done", False):
                input_tokens = chunk.get("prompt_eval_count", 0) or 0
                output_tokens = chunk.get("eval_count", 0) or 0

        # End line if we printed content
        if printed_prefix or is_thinking:
            sys.stdout.write(f"{C.RESET}\n")
            sys.stdout.flush()

        content = "".join(content_parts)
        thinking = "".join(thinking_parts)

        result = {
            "role": "assistant",
            "content": content,
            "tool_calls": tool_calls,
            "thinking": thinking,
            "_input_tokens": input_tokens,
            "_output_tokens": output_tokens,
        }
        return result

    def _extract_message(self, response) -> Dict:
        """Extract message dict from ChatResponse."""
        msg = response.get("message", {})
        if hasattr(msg, "model_dump"):
            return msg.model_dump()
        if isinstance(msg, dict):
            return msg
        return {
            "role": getattr(msg, "role", "assistant"),
            "content": getattr(msg, "content", ""),
            "tool_calls": getattr(msg, "tool_calls", None),
            "thinking": getattr(msg, "thinking", ""),
        }


def parse_tool_calls_from_text(content: str) -> List[Dict]:
    """Parse ACTION: {...} blocks from model text output."""
    if not content:
        return []
    
    tool_calls = []
    # Match ACTION: followed by JSON on the same line
    pattern = r'ACTION:\s*(\{[^\n]+\})'
    matches = re.findall(pattern, content)
    
    for match in matches:
        try:
            parsed = json.loads(match)
            name = parsed.get("name", "")
            arguments = parsed.get("arguments", {})
            if name:
                tool_calls.append({
                    "function": {
                        "name": name,
                        "arguments": arguments,
                    }
                })
        except json.JSONDecodeError:
            continue
    
    return tool_calls
