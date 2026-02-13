
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from nexus.config import config

class LLMProvider(ABC):
    @abstractmethod
    def chat(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict]] = None) -> Any:
        pass

class OllamaProvider(LLMProvider):
    def __init__(self):
        from openai import OpenAI
        self.client = OpenAI(
            base_url=config.OLLAMA_BASE_URL,
            api_key="ollama"
        )
        self.model = config.OLLAMA_MODEL

    def chat(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict]] = None) -> Any:
        # Convert tools to Ollama format if needed (usually same as OpenAI)
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

    def chat(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict]] = None) -> Any:
        # Llama.cpp supports OpenAI-like formatting in newer versions
        # Check if tools are supported in this version wrapper
        try:
            kwargs = {}
            if tools:
                # Helper to convert tools if needed, but standard create_chat_completion supports it now
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            return self.client.create_chat_completion(
                messages=messages,
                temperature=0.7,
                **kwargs
            )
        except Exception as e:
            # Fallback if tools not supported directly
            print(f"[LlamaCpp] Warning: Tool/Chat Error: {e}")
            return self.client.create_chat_completion(
                 messages=messages,
                 temperature=0.7
            )
