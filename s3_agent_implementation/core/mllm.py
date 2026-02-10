"""
MLLM Agent - Wrapper around LLM engines for agent interactions.
Handles message formatting for different providers.
"""

import base64
from typing import Optional, List, Dict, Any
from io import BytesIO
from PIL import Image

from .engine import (
    LMMEngine,
    LMMEngineOpenAI,
    LMMEngineAnthropic,
    LMMEngineOllama,
    LMMEngineGemini
)


class LMMAgent:
    """Agent wrapper for LMM interactions."""
    
    def __init__(self, engine_params: Optional[Dict] = None, 
                 system_prompt: Optional[str] = None,
                 engine: Optional[LMMEngine] = None):
        """
        Initialize LMM Agent.
        
        Args:
            engine_params: Parameters for creating engine (if engine not provided)
            system_prompt: System prompt to initialize with
            engine: Pre-created engine instance
        """
        if engine is None:
            if engine_params is not None:
                engine_type = engine_params.get("engine_type")
                if engine_type == "openai":
                    self.engine = LMMEngineOpenAI(**engine_params)
                elif engine_type == "anthropic":
                    self.engine = LMMEngineAnthropic(**engine_params)
                elif engine_type == "ollama":
                    self.engine = LMMEngineOllama(**engine_params)
                elif engine_type == "gemini":
                    self.engine = LMMEngineGemini(**engine_params)
                else:
                    raise ValueError(f"engine_type '{engine_type}' is not supported")
            else:
                raise ValueError("engine_params must be provided if engine is None")
        else:
            self.engine = engine
        
        self.messages: List[Dict] = []
        self.system_prompt = system_prompt or "You are a helpful assistant."
        
        # Initialize with system prompt
        self.add_system_prompt(self.system_prompt)
    
    def encode_image(self, image_content) -> str:
        """Encode image to base64 string."""
        if isinstance(image_content, str):
            # Assume it's a file path
            with open(image_content, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode("utf-8")
        else:
            # Assume it's bytes
            return base64.b64encode(image_content).decode("utf-8")
    
    def reset(self):
        """Reset message history while keeping system prompt."""
        self.messages = [
            {
                "role": "system",
                "content": [{"type": "text", "text": self.system_prompt}]
            }
        ]
    
    def add_system_prompt(self, system_prompt: str):
        """Add or update system prompt."""
        self.system_prompt = system_prompt
        if len(self.messages) > 0:
            self.messages[0] = {
                "role": "system",
                "content": [{"type": "text", "text": system_prompt}]
            }
        else:
            self.messages.append({
                "role": "system",
                "content": [{"type": "text", "text": system_prompt}]
            })
    
    def remove_message_at(self, index: int):
        """Remove message at given index."""
        if index < len(self.messages):
            self.messages.pop(index)
    
    def replace_message_at(self, index: int, text_content: str, 
                          image_content=None, image_detail: str = "high"):
        """Replace message at given index."""
        if index < len(self.messages):
            self.messages[index] = {
                "role": self.messages[index]["role"],
                "content": [{"type": "text", "text": text_content}]
            }
            if image_content:
                base64_image = self.encode_image(image_content)
                self.messages[index]["content"].append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{base64_image}",
                        "detail": image_detail
                    }
                })
    
    def add_message(self, text_content: str, image_content=None, 
                   role: Optional[str] = None, image_detail: str = "high",
                   put_text_last: bool = False):
        """
        Add a new message to history.
        
        Args:
            text_content: Text content
            image_content: Image (bytes, path, or PIL Image)
            role: "user", "assistant", or None (auto-detect)
            image_detail: "high", "low", or "auto"
            put_text_last: Whether to put text after images
        """
        # Auto-detect role if not provided
        if role is None:
            if self.messages[-1]["role"] == "system":
                role = "user"
            elif self.messages[-1]["role"] == "user":
                role = "assistant"
            elif self.messages[-1]["role"] == "assistant":
                role = "user"
        
        # Handle different engine formats
        if isinstance(self.engine, LMMEngineAnthropic):
            # Anthropic format
            message = {
                "role": role,
                "content": [{"type": "text", "text": text_content}]
            }
            
            if image_content:
                if isinstance(image_content, list):
                    for image in image_content:
                        base64_image = self.encode_image(image)
                        message["content"].append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": base64_image
                            }
                        })
                else:
                    base64_image = self.encode_image(image_content)
                    message["content"].append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": base64_image
                        }
                    })
        else:
            # OpenAI-compatible format (OpenAI, Ollama, Gemini, etc.)
            message = {
                "role": role,
                "content": [{"type": "text", "text": text_content}]
            }
            
            if image_content:
                if isinstance(image_content, list):
                    for image in image_content:
                        base64_image = self.encode_image(image)
                        message["content"].append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}",
                                "detail": image_detail
                            }
                        })
                else:
                    base64_image = self.encode_image(image_content)
                    message["content"].append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64_image}",
                            "detail": image_detail
                        }
                    })
        
        # Rotate text to end if requested
        if put_text_last and len(message["content"]) > 1:
            text_content = message["content"].pop(0)
            message["content"].append(text_content)
        
        self.messages.append(message)
    
    def get_response(self, user_message: Optional[str] = None,
                    messages: Optional[List[Dict]] = None,
                    temperature: float = 0.0,
                    max_new_tokens: Optional[int] = None,
                    use_thinking: bool = False,
                    **kwargs) -> str:
        """
        Generate response from LLM.
        
        Args:
            user_message: Optional user message to add
            messages: Optional messages to use (defaults to self.messages)
            temperature: Sampling temperature
            max_new_tokens: Max tokens to generate
            use_thinking: Whether to use thinking mode (Anthropic only)
            **kwargs: Additional args
            
        Returns:
            Generated text response
        """
        if messages is None:
            messages = self.messages
        
        if user_message:
            messages.append({
                "role": "user",
                "content": [{"type": "text", "text": user_message}]
            })
        
        # Use thinking mode if requested and available
        if use_thinking and hasattr(self.engine, 'generate_with_thinking'):
            return self.engine.generate_with_thinking(
                messages,
                temperature=temperature,
                max_new_tokens=max_new_tokens,
                **kwargs
            )
        
        return self.engine.generate(
            messages,
            temperature=temperature,
            max_new_tokens=max_new_tokens,
            **kwargs
        )


__all__ = ['LMMAgent']
