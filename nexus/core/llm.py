"""
LLM Providers — Multi-provider abstraction for chat + tool-calling.

Supports: Ollama, Llama.cpp, OpenAI, Anthropic, Groq, Gemini.
All cloud providers use OpenAI-compatible SDK where possible.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from nexus.config import config


class LLMProvider(ABC):
    @abstractmethod
    def chat(self, messages: List[Dict[str, Any]],
             tools: Optional[List[Dict]] = None) -> Any:
        pass


# ═══════════════════════════════════════════════════════════════════════
#  Ollama (via OpenAI-compatible endpoint)
# ═══════════════════════════════════════════════════════════════════════

class OllamaProvider(LLMProvider):
    def __init__(self):
        from openai import OpenAI
        self.client = OpenAI(
            base_url=config.OLLAMA_BASE_URL,
            api_key="ollama"
        )
        self.model = config.OLLAMA_MODEL

    def chat(self, messages: List[Dict[str, Any]],
             tools: Optional[List[Dict]] = None) -> Any:
        kwargs = {}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
            
        return self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.7,
            **kwargs
        )


# ═══════════════════════════════════════════════════════════════════════
#  Llama.cpp (local GGUF)
# ═══════════════════════════════════════════════════════════════════════

class LlamaCppProvider(LLMProvider):
    def __init__(self):
        try:
            from llama_cpp import Llama
            self.client = Llama(
                model_path=config.LLAMA_CPP_PATH,
                n_ctx=config.LLAMA_CPP_N_CTX,
                n_gpu_layers=config.LLAMA_CPP_N_GPU_LAYERS,
                verbose=False
            )
        except ImportError:
            raise ImportError("llama-cpp-python not installed.")

    def chat(self, messages: List[Dict[str, Any]],
             tools: Optional[List[Dict]] = None) -> Any:
        try:
            kwargs = {}
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            return self.client.create_chat_completion(
                messages=messages,
                temperature=0.7,
                **kwargs
            )
        except Exception as e:
            print(f"[LlamaCpp] Warning: Tool/Chat Error: {e}")
            return self.client.create_chat_completion(
                 messages=messages,
                 temperature=0.7
            )


# ═══════════════════════════════════════════════════════════════════════
#  OpenAI (GPT-4o, GPT-4o-mini)
# ═══════════════════════════════════════════════════════════════════════

class OpenAIProvider(LLMProvider):
    def __init__(self):
        from openai import OpenAI
        if not config.OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY not set. "
                "Set it in environment or nexus/config.py"
            )
        self.client = OpenAI(
            api_key=config.OPENAI_API_KEY,
            base_url=config.OPENAI_BASE_URL,
        )
        self.model = config.OPENAI_MODEL

    def chat(self, messages: List[Dict[str, Any]],
             tools: Optional[List[Dict]] = None) -> Any:
        kwargs = {}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
            
        return self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.7,
            **kwargs
        )


# ═══════════════════════════════════════════════════════════════════════
#  Anthropic (Claude 3.5 Sonnet, Claude 3 Haiku)
# ═══════════════════════════════════════════════════════════════════════

class AnthropicProvider(LLMProvider):
    def __init__(self):
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "anthropic not installed. Install with: pip install anthropic"
            )
        
        if not config.ANTHROPIC_API_KEY:
            raise ValueError(
                "ANTHROPIC_API_KEY not set. "
                "Set it in environment or nexus/config.py"
            )
        self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self.model = config.ANTHROPIC_MODEL

    def _convert_tools_to_anthropic(self, tools: List[Dict]) -> List[Dict]:
        """Convert OpenAI tool format to Anthropic format."""
        anthropic_tools = []
        for tool in tools:
            func = tool.get("function", {})
            anthropic_tools.append({
                "name": func.get("name", ""),
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {}),
            })
        return anthropic_tools

    def chat(self, messages: List[Dict[str, Any]],
             tools: Optional[List[Dict]] = None) -> Any:
        # Extract system message
        system_text = ""
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_text += (msg.get("content") or "") + "\n"
            elif msg["role"] == "tool":
                # Convert tool results to Anthropic format
                chat_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.get("tool_call_id", ""),
                        "content": msg.get("content", ""),
                    }]
                })
            elif msg["role"] == "assistant" and msg.get("tool_calls"):
                # Convert assistant tool calls to Anthropic format
                content_blocks = []
                if msg.get("content"):
                    content_blocks.append({
                        "type": "text",
                        "text": msg["content"],
                    })
                for tc in msg["tool_calls"]:
                    func = tc.get("function", {})
                    import json
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": func.get("name", ""),
                        "input": json.loads(func.get("arguments", "{}")),
                    })
                chat_messages.append({
                    "role": "assistant",
                    "content": content_blocks,
                })
            else:
                chat_messages.append({
                    "role": msg["role"],
                    "content": msg.get("content") or "",
                })

        kwargs = {}
        if tools:
            kwargs["tools"] = self._convert_tools_to_anthropic(tools)

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system_text.strip(),
            messages=chat_messages,
            **kwargs,
        )

        # Convert Anthropic response to OpenAI-like format
        return self._convert_response(response)

    def _convert_response(self, response) -> Dict:
        """Convert Anthropic response to OpenAI-compatible dict."""
        import json
        
        content_text = ""
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                content_text += block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "type": "function",
                    "function": {
                        "name": block.name,
                        "arguments": json.dumps(block.input),
                    }
                })

        message = {
            "role": "assistant",
            "content": content_text or None,
        }
        if tool_calls:
            message["tool_calls"] = tool_calls

        return {
            "choices": [{"message": message}],
            "usage": {
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
            }
        }


# ═══════════════════════════════════════════════════════════════════════
#  Groq (OpenAI-compatible, ultra-fast)
# ═══════════════════════════════════════════════════════════════════════

class GroqProvider(LLMProvider):
    def __init__(self):
        from openai import OpenAI
        if not config.GROQ_API_KEY:
            raise ValueError(
                "GROQ_API_KEY not set. "
                "Set it in environment or nexus/config.py"
            )
        self.client = OpenAI(
            api_key=config.GROQ_API_KEY,
            base_url=config.GROQ_BASE_URL,
        )
        self.model = config.GROQ_MODEL

    def chat(self, messages: List[Dict[str, Any]],
             tools: Optional[List[Dict]] = None) -> Any:
        kwargs = {}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
            
        return self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.7,
            **kwargs
        )


# ═══════════════════════════════════════════════════════════════════════
#  Google Gemini (OpenAI-compatible endpoint)
# ═══════════════════════════════════════════════════════════════════════

class GeminiProvider(LLMProvider):
    def __init__(self):
        from openai import OpenAI
        if not config.GEMINI_API_KEY:
            raise ValueError(
                "GEMINI_API_KEY not set. "
                "Set it in environment or nexus/config.py"
            )
        self.client = OpenAI(
            api_key=config.GEMINI_API_KEY,
            base_url=config.GEMINI_BASE_URL,
        )
        self.model = config.GEMINI_MODEL

    def chat(self, messages: List[Dict[str, Any]],
             tools: Optional[List[Dict]] = None) -> Any:
        kwargs = {}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
            
        return self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.7,
            **kwargs
        )


# ═══════════════════════════════════════════════════════════════════════
#  Factory
# ═══════════════════════════════════════════════════════════════════════

PROVIDERS = {
    "ollama": OllamaProvider,
    "llamacpp": LlamaCppProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "groq": GroqProvider,
    "gemini": GeminiProvider,
}


def create_provider(name: Optional[str] = None) -> LLMProvider:
    """Create an LLM provider by name. Defaults to config.LLM_PROVIDER."""
    provider_name = (name or config.LLM_PROVIDER).lower().strip()
    
    cls = PROVIDERS.get(provider_name)
    if cls is None:
        available = ", ".join(PROVIDERS.keys())
        raise ValueError(
            f"Unknown LLM provider: '{provider_name}'. "
            f"Available: {available}"
        )
    
    return cls()
