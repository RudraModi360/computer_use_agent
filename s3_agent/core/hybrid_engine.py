"""
Hybrid Vision Engine for S3 Agent
Uses OpenRouter (UI-TARS) for vision with Groq fallback
Ollama for text-only tasks
"""

import os
import base64
import backoff
from typing import Optional, Dict, Any, List
from openai import OpenAI
from groq import Groq


class HybridVisionEngine:
    """
    Hybrid engine that routes requests optimally:
    - Vision tasks: OpenRouter (UI-TARS) → Groq fallback
    - Text tasks: Ollama (local)
    """
    
    def __init__(
        self,
        openrouter_key: Optional[str] = None,
        groq_key: Optional[str] = None,
        ollama_base_url: str = "http://localhost:11434/v1",
        openrouter_model: str = "bytedance/ui-tars-1.5-7b",
        groq_model: str = "meta-llama/llama-4-scout-17b-16e-instruct",
        ollama_model: str = "gpt-oss:20b-cloud",
        site_url: str = "https://localhost",
        site_name: str = "S3-Agent"
    ):
        """
        Initialize hybrid engine
        
        Args:
            openrouter_key: OpenRouter API key (free tier: 50 req/day)
            groq_key: Groq API key (fallback for vision)
            ollama_base_url: Local Ollama endpoint
            openrouter_model: UI-TARS model
            groq_model: Vision model for fallback
            ollama_model: Fast text model
        """
        # OpenRouter client (primary for vision)
        self.openrouter_key = openrouter_key or os.getenv("OPENROUTER_API_KEY")
        self.openrouter_client = None
        if self.openrouter_key:
            self.openrouter_client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=self.openrouter_key
            )
        self.openrouter_model = openrouter_model
        self.openrouter_headers = {
            "HTTP-Referer": site_url,
            "X-Title": site_name
        }
        
        # Groq client (fallback for vision)
        self.groq_key = groq_key or os.getenv("GROQ_API_KEY")
        self.groq_client = None
        if self.groq_key:
            self.groq_client = Groq(api_key=self.groq_key)
        self.groq_model = groq_model
        
        # Ollama client (text-only, fast)
        self.ollama_base_url = ollama_base_url
        self.ollama_model = ollama_model
        self.ollama_client = OpenAI(
            base_url=ollama_base_url,
            api_key="ollama"
        )
        
        # Request tracking for rate limiting
        self.openrouter_count = 0
        self.openrouter_limit = 50  # Free tier limit
        self.use_openrouter = False  # Prioritize Groq as requested
        
    def encode_image(self, image_path_or_bytes) -> str:
        """Encode image to base64"""
        if isinstance(image_path_or_bytes, str):
            with open(image_path_or_bytes, "rb") as f:
                return base64.b64encode(f.read()).decode('utf-8')
        else:
            return base64.b64encode(image_path_or_bytes).decode('utf-8')
    
    def generate_text(
        self,
        messages: List[Dict],
        temperature: float = 0.0,
        max_tokens: int = 512
    ) -> str:
        """
        Generate text using Ollama (fast, local)
        Use this for: reasoning, action selection, planning
        """
        response = self.ollama_client.chat.completions.create(
            model=self.ollama_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        return response.choices[0].message.content
    
    def generate_vision(
        self,
        messages: List[Dict],
        temperature: float = 0.0,
        max_tokens: int = 512
    ) -> str:
        """
        Generate with vision using OpenRouter → Groq fallback
        Use this for: screenshot analysis, element detection
        
        Tries OpenRouter first, falls back to Groq on 429 or error
        """
        # Try Groq first as requested
        if self.groq_client:
            try:
                return self._try_groq(messages, temperature, max_tokens)
            except Exception as e:
                print(f"  [Groq] Error: {e}, attempting OpenRouter fallback")
        
        # Fallback to OpenRouter if available and under limit
        if self.use_openrouter and self.openrouter_client and self.openrouter_count < self.openrouter_limit:
            try:
                result = self._try_openrouter(messages, temperature, max_tokens)
                self.openrouter_count += 1
                print(f"  [OpenRouter] Request {self.openrouter_count}/{self.openrouter_limit}")
                return result
            except Exception as e:
                print(f"  [OpenRouter] Error: {e}")
        
        raise Exception("No vision API available (both Groq and OpenRouter failed)")
    
    def _try_openrouter(
        self,
        messages: List[Dict],
        temperature: float,
        max_tokens: int
    ) -> str:
        """Try OpenRouter API"""
        response = self.openrouter_client.chat.completions.create(
            extra_headers=self.openrouter_headers,
            model=self.openrouter_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        return response.choices[0].message.content
    
    def _try_groq(
        self,
        messages: List[Dict],
        temperature: float,
        max_tokens: int
    ) -> str:
        """Try Groq API"""
        print("  [Groq] Using fallback vision model")
        response = self.groq_client.chat.completions.create(
            model=self.groq_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        return response.choices[0].message.content
    
    def analyze_screenshot(
        self,
        screenshot_bytes: bytes,
        task_description: str = "Analyze this UI screenshot",
        extract_elements: bool = True
    ) -> Dict[str, Any]:
        """
        Analyze screenshot and extract UI elements
        
        Args:
            screenshot_bytes: Raw screenshot bytes
            task_description: What to look for
            extract_elements: Whether to extract element list
            
        Returns:
            Dictionary with analysis results
        """
        # Encode image
        base64_image = self.encode_image(screenshot_bytes)
        
        # Build prompt
        if extract_elements:
            prompt = f"""{task_description}

List all interactive UI elements (buttons, inputs, links, menus) with:
1. Element type (button/input/link/text)
2. Text label
3. Approximate center coordinates (x, y)

Format:
- [TYPE] "text" at (x, y)

Be concise."""
        else:
            prompt = task_description
        
        # Create message with image
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64_image}"
                        }
                    }
                ]
            }
        ]
        
        # Generate with vision
        start_time = __import__('time').time()
        response = self.generate_vision(messages)
        elapsed = __import__('time').time() - start_time
        
        return {
            'response': response,
            'time': elapsed,
            'provider': 'openrouter' if self.openrouter_count <= self.openrouter_limit else 'groq',
            'openrouter_requests_used': self.openrouter_count
        }
    
    def get_status(self) -> Dict:
        """Get current engine status"""
        return {
            'openrouter_available': self.openrouter_client is not None,
            'openrouter_requests_used': self.openrouter_count,
            'openrouter_requests_remaining': max(0, self.openrouter_limit - self.openrouter_count),
            'groq_available': self.groq_client is not None,
            'ollama_available': True,
            'current_vision_provider': 'openrouter' if self.use_openrouter else 'groq'
        }


class HybridAgent:
    """Agent that uses hybrid engine for optimal performance"""
    
    def __init__(self, engine: Optional[HybridVisionEngine] = None):
        self.engine = engine or HybridVisionEngine()
        
    def process_step(
        self,
        screenshot_bytes: bytes,
        task: str,
        history: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Process one automation step
        
        Workflow:
        1. Vision analysis (OpenRouter/Groq) - identify elements
        2. Text reasoning (Ollama) - decide action
        3. Return structured action
        """
        import time
        
        total_start = time.time()
        
        # Step 1: Vision analysis (uses cloud API)
        print("  [1/3] Vision analysis...")
        vision_start = time.time()
        vision_result = self.engine.analyze_screenshot(
            screenshot_bytes,
            task_description=f"Task: {task}\n\nIdentify all clickable UI elements.",
            extract_elements=True
        )
        vision_time = time.time() - vision_start
        
        # Step 2: Text reasoning (uses local Ollama)
        print("  [2/3] Reasoning...")
        reasoning_start = time.time()
        
        reasoning_prompt = f"""You are a GUI automation agent.

Task: {task}

Screen elements detected:
{vision_result['response']}

Action history: {history or 'None'}

Based on the screen elements above, what action should I take?

Available actions:
- CLICK(x, y) - Click at coordinates
- TYPE(text) - Type text
- SCROLL(direction) - Scroll up/down
- WAIT - Wait for loading
- DONE - Task complete

Respond in this exact format:
ACTION: <ACTION>
REASON: <brief explanation>"""

        reasoning_result = self.engine.generate_text([
            {"role": "user", "content": reasoning_prompt}
        ])
        reasoning_time = time.time() - reasoning_start
        
        # Step 3: Parse action
        print("  [3/3] Parsing action...")
        action = self._parse_action(reasoning_result)
        
        total_time = time.time() - total_start
        
        return {
            'vision_analysis': vision_result['response'],
            'vision_time': vision_time,
            'reasoning': reasoning_result,
            'reasoning_time': reasoning_time,
            'action': action,
            'total_time': total_time,
            'api_status': self.engine.get_status()
        }
    
    def _parse_action(self, reasoning: str) -> Dict[str, Any]:
        """Parse action from reasoning output"""
        action = {
            'type': 'UNKNOWN',
            'params': {},
            'raw': reasoning
        }
        
        # Extract ACTION line
        for line in reasoning.split('\n'):
            line = line.strip()
            if line.startswith('ACTION:'):
                action_str = line.replace('ACTION:', '').strip()
                
                # Parse different action types
                if 'CLICK' in action_str.upper():
                    import re
                    coords = re.findall(r'\((\d+),\s*(\d+)\)', action_str)
                    if coords:
                        action['type'] = 'CLICK'
                        action['params'] = {
                            'x': int(coords[0][0]),
                            'y': int(coords[0][1])
                        }
                elif 'TYPE' in action_str.upper():
                    text = action_str.split('(', 1)[-1].rstrip(')')
                    action['type'] = 'TYPE'
                    action['params'] = {'text': text}
                elif 'SCROLL' in action_str.upper():
                    direction = 'UP' if 'UP' in action_str.upper() else 'DOWN'
                    action['type'] = 'SCROLL'
                    action['params'] = {'direction': direction}
                elif 'DONE' in action_str.upper():
                    action['type'] = 'DONE'
                elif 'WAIT' in action_str.upper():
                    action['type'] = 'WAIT'
                
                break
        
        return action


if __name__ == "__main__":
    # Test the hybrid engine
    print("="*60)
    print("HYBRID VISION ENGINE TEST")
    print("="*60)
    
    # Initialize
    engine = HybridVisionEngine(
        openrouter_key="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",
        ollama_model="qwen2.5:0.5b"
    )
    
    # Check status
    status = engine.get_status()
    print("\nEngine Status:")
    for key, value in status.items():
        print(f"  {key}: {value}")
    
    # Test text generation (Ollama)
    print("\n" + "="*60)
    print("TEST 1: Text Generation (Ollama)")
    print("="*60)
    
    try:
        import time
        start = time.time()
        text_result = engine.generate_text([
            {"role": "user", "content": "What is 2+2? Answer in one word."}
        ])
        elapsed = time.time() - start
        print(f"  Time: {elapsed:.2f}s")
        print(f"  Response: {text_result.strip()}")
    except Exception as e:
        print(f"  Error: {e}")
    
    # Test vision if screenshot available
    print("\n" + "="*60)
    print("TEST 2: Vision Analysis (OpenRouter/Groq)")
    print("="*60)
    
    # Create test screenshot
    from PIL import Image, ImageDraw
    img = Image.new('RGB', (800, 600), color='white')
    draw = ImageDraw.Draw(img)
    draw.rectangle([100, 100, 300, 150], fill='blue', outline='black')
    draw.text((120, 115), "Submit", fill='white')
    draw.rectangle([350, 100, 550, 150], fill='gray', outline='black')
    draw.text((370, 115), "Cancel", fill='black')
    
    import io
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    
    try:
        result = engine.analyze_screenshot(
            img_bytes.getvalue(),
            task_description="Identify all buttons and their coordinates"
        )
        print(f"  Time: {result['time']:.2f}s")
        print(f"  Provider: {result['provider']}")
        print(f"  OpenRouter requests used: {result['openrouter_requests_used']}")
        print(f"  Response preview:")
        for line in result['response'].split('\n')[:5]:
            if line.strip():
                print(f"    {line[:80]}")
    except Exception as e:
        print(f"  Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*60)
    print("TEST COMPLETE")
    print("="*60)
