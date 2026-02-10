"""
Core LLM Engine implementations for S3 Agent.
Supports multiple providers: OpenAI, Anthropic, Gemini, Azure, Ollama, etc.
"""

import os
import backoff
from typing import Optional, Dict, Any


class LMMEngine:
    """Base class for LMM engines."""
    pass


class LMMEngineOpenAI(LMMEngine):
    """OpenAI API engine."""
    
    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None,
                 model: Optional[str] = None, rate_limit: int = -1,
                 temperature: Optional[float] = None, organization: Optional[str] = None,
                 **kwargs):
        assert model is not None, "model must be provided"
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.organization = organization
        self.request_interval = 0 if rate_limit == -1 else 60.0 / rate_limit
        self.llm_client = None
        self.temperature = temperature
        
        # Import here to avoid dependency issues
        try:
            from openai import OpenAI, APIConnectionError, APIError, RateLimitError
            self._openai_imports = {
                'OpenAI': OpenAI,
                'APIConnectionError': APIConnectionError,
                'APIError': APIError,
                'RateLimitError': RateLimitError
            }
        except ImportError:
            raise ImportError("openai package not installed. Install with: pip install openai")
    
    @backoff.on_exception(backoff.expo, Exception, max_time=60)
    def generate(self, messages, temperature: float = 0.0, max_new_tokens: Optional[int] = None, **kwargs):
        """Generate response from OpenAI API."""
        api_key = self.api_key or os.getenv("OPENAI_API_KEY")
        if api_key is None:
            raise ValueError("OpenAI API key required")
        
        organization = self.organization or os.getenv("OPENAI_ORG_ID")
        
        if not self.llm_client:
            if not self.base_url:
                self.llm_client = self._openai_imports['OpenAI'](api_key=api_key, organization=organization)
            else:
                self.llm_client = self._openai_imports['OpenAI'](base_url=self.base_url, api_key=api_key, organization=organization)
        
        temp = temperature if self.temperature is None else self.temperature
        
        response = self.llm_client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temp,
            max_tokens=max_new_tokens if max_new_tokens else 4096,
            **kwargs
        )
        return response.choices[0].message.content


class LMMEngineAnthropic(LMMEngine):
    """Anthropic Claude engine."""
    
    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None,
                 model: Optional[str] = None, thinking: bool = False,
                 temperature: Optional[float] = None, **kwargs):
        assert model is not None, "model must be provided"
        self.model = model
        self.thinking = thinking
        self.api_key = api_key
        self.llm_client = None
        self.temperature = temperature
        
        try:
            from anthropic import Anthropic
            self._anthropic = Anthropic
        except ImportError:
            raise ImportError("anthropic package not installed. Install with: pip install anthropic")
    
    @backoff.on_exception(backoff.expo, Exception, max_time=60)
    def generate(self, messages, temperature: float = 0.0, max_new_tokens: Optional[int] = None, **kwargs):
        """Generate response from Anthropic API."""
        api_key = self.api_key or os.getenv("ANTHROPIC_API_KEY")
        if api_key is None:
            raise ValueError("Anthropic API key required")
        
        self.llm_client = self._anthropic(api_key=api_key)
        temp = self.temperature if temperature is None else temperature
        
        # Extract system message
        system_msg = None
        api_messages = []
        for msg in messages:
            if msg['role'] == 'system':
                system_msg = msg['content'][0]['text'] if isinstance(msg['content'], list) else msg['content']
            else:
                api_messages.append(msg)
        
        response = self.llm_client.messages.create(
            model=self.model,
            system=system_msg or "You are a helpful assistant.",
            messages=api_messages,
            max_tokens=max_new_tokens if max_new_tokens else 4096,
            temperature=temp,
            **kwargs
        )
        return response.content[0].text
    
    @backoff.on_exception(backoff.expo, Exception, max_time=60)
    def generate_with_thinking(self, messages, temperature: float = 0.0, max_new_tokens: Optional[int] = None, **kwargs):
        """Generate with thinking tokens enabled (Claude 3.7+)."""
        api_key = self.api_key or os.getenv("ANTHROPIC_API_KEY")
        if api_key is None:
            raise ValueError("Anthropic API key required")
        
        self.llm_client = self._anthropic(api_key=api_key)
        
        # Extract system message
        system_msg = None
        api_messages = []
        for msg in messages:
            if msg['role'] == 'system':
                system_msg = msg['content'][0]['text'] if isinstance(msg['content'], list) else msg['content']
            else:
                api_messages.append(msg)
        
        response = self.llm_client.messages.create(
            model=self.model,
            system=system_msg or "You are a helpful assistant.",
            messages=api_messages,
            max_tokens=max_new_tokens if max_new_tokens else 8192,
            temperature=temperature,
            thinking={"type": "enabled", "budget_tokens": 4096},
            **kwargs
        )
        
        thoughts = response.content[0].thinking
        answer = response.content[1].text
        full_response = f"<thoughts>\n{thoughts}\n</thoughts>\n\n<answer>\n{answer}\n</answer>\n"
        return full_response


class LMMEngineOllama(LMMEngine):
    """Ollama local inference engine."""
    
    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None,
                 model: Optional[str] = None, rate_limit: int = -1,
                 temperature: Optional[float] = None, **kwargs):
        assert model is not None, "Ollama model name must be provided"
        self.model = model
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        self.api_key = api_key or os.getenv("OLLAMA_API_KEY", "ollama")
        self.request_interval = 0 if rate_limit == -1 else 60.0 / rate_limit
        self.llm_client = None
        self.temperature = temperature
        
        try:
            from openai import OpenAI
            self._openai = OpenAI
        except ImportError:
            raise ImportError("openai package required for Ollama compatibility")
    
    @backoff.on_exception(backoff.expo, Exception, max_time=60)
    def generate(self, messages, temperature: float = 0.0, max_new_tokens: Optional[int] = None, **kwargs):
        """Generate response from Ollama API."""
        if not self.llm_client:
            self.llm_client = self._openai(base_url=self.base_url, api_key=self.api_key)
        
        temp = self.temperature if self.temperature is not None else temperature
        
        response = self.llm_client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_new_tokens if max_new_tokens else 4096,
            temperature=temp,
            **kwargs
        )
        return response.choices[0].message.content


class LMMEngineGemini(LMMEngine):
    """Google Gemini engine."""
    
    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None,
                 model: Optional[str] = None, rate_limit: int = -1,
                 temperature: Optional[float] = None, **kwargs):
        assert model is not None, "model must be provided"
        self.model = model
        self.base_url = base_url or os.getenv("GEMINI_ENDPOINT_URL")
        self.api_key = api_key
        self.request_interval = 0 if rate_limit == -1 else 60.0 / rate_limit
        self.llm_client = None
        self.temperature = temperature
        
        try:
            from openai import OpenAI
            self._openai = OpenAI
        except ImportError:
            raise ImportError("openai package required for Gemini compatibility")
    
    @backoff.on_exception(backoff.expo, Exception, max_time=60)
    def generate(self, messages, temperature: float = 0.0, max_new_tokens: Optional[int] = None, **kwargs):
        """Generate response from Gemini API."""
        api_key = self.api_key or os.getenv("GEMINI_API_KEY")
        if api_key is None:
            raise ValueError("Gemini API key required")
        
        base_url = self.base_url or os.getenv("GEMINI_ENDPOINT_URL")
        if base_url is None:
            raise ValueError("Gemini endpoint URL required")
        
        if not self.llm_client:
            self.llm_client = self._openai(base_url=base_url, api_key=api_key)
        
        temp = self.temperature if self.temperature is not None else temperature
        
        response = self.llm_client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_new_tokens if max_new_tokens else 4096,
            temperature=temp,
            **kwargs
        )
        return response.choices[0].message.content


# Export all engines
__all__ = [
    'LMMEngine',
    'LMMEngineOpenAI',
    'LMMEngineAnthropic',
    'LMMEngineOllama',
    'LMMEngineGemini'
]
