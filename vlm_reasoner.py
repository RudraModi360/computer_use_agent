"""
Tier 2: VLM Reasoner Module
Lightweight VLM integration via llama.cpp or Ollama.
"""

import os
import base64
import json
import time
import requests
from typing import List, Dict, Optional, Tuple, Union
from abc import ABC, abstractmethod
from dataclasses import dataclass

from prompts import SYSTEM_PROMPT, build_task_prompt, build_feedback_prompt, parse_action


@dataclass
class VLMResponse:
    """Structured response from VLM."""
    raw_response: str
    action: dict
    reasoning: str
    inference_time: float


class VLMBackend(ABC):
    """Abstract base class for VLM backends."""
    
    @abstractmethod
    def generate(self, prompt: str, images: List[str], **kwargs) -> str:
        """Generate response from VLM."""
        pass


class OllamaBackend(VLMBackend):
    """Ollama API backend."""
    
    def __init__(self, 
                 model: str = "llava:7b",
                 host: str = "http://localhost:11434",
                 timeout: int = 60):
        self.model = model
        self.host = host
        self.timeout = timeout
        self.api_url = f"{host}/api/generate"
    
    def generate(self, prompt: str, images: List[str], **kwargs) -> str:
        """
        Generate response using Ollama API.
        
        Args:
            prompt: Text prompt
            images: List of image paths or base64 strings
        """
        # Encode images to base64
        encoded_images = []
        for img_path in images:
            if os.path.exists(img_path):
                with open(img_path, 'rb') as f:
                    encoded = base64.b64encode(f.read()).decode('utf-8')
                    encoded_images.append(encoded)
            elif img_path.startswith('data:') or len(img_path) > 1000:
                # Already base64
                encoded_images.append(img_path.split(',')[-1] if ',' in img_path else img_path)
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "images": encoded_images,
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_predict": 512,
            }
        }
        
        try:
            response = requests.post(self.api_url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            result = response.json()
            return result.get('response', '')
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Ollama API error: {e}")


class LlamaCppBackend(VLMBackend):
    """llama.cpp Python backend using llama-cpp-python."""
    
    def __init__(self,
                 model_path: str,
                 n_ctx: int = 4096,
                 n_gpu_layers: int = -1,
                 clip_model_path: str = None):
        """
        Initialize llama.cpp backend.
        
        Args:
            model_path: Path to GGUF model file
            n_ctx: Context window size
            n_gpu_layers: Number of layers to offload to GPU (-1 for all)
            clip_model_path: Path to CLIP model for vision (mmproj file)
        """
        try:
            from llama_cpp import Llama
            from llama_cpp.llama_chat_format import Llava15ChatHandler
        except ImportError:
            raise ImportError("llama-cpp-python not installed. Run: pip install llama-cpp-python")
        
        self.model_path = model_path
        
        # Initialize with vision support if clip model provided
        if clip_model_path:
            chat_handler = Llava15ChatHandler(clip_model_path=clip_model_path)
            self.llm = Llama(
                model_path=model_path,
                n_ctx=n_ctx,
                n_gpu_layers=n_gpu_layers,
                chat_handler=chat_handler,
                logits_all=True,
            )
        else:
            self.llm = Llama(
                model_path=model_path,
                n_ctx=n_ctx,
                n_gpu_layers=n_gpu_layers,
            )
    
    def generate(self, prompt: str, images: List[str], **kwargs) -> str:
        """Generate response using llama.cpp."""
        # Build messages with images
        image_contents = []
        for img_path in images:
            if os.path.exists(img_path):
                with open(img_path, 'rb') as f:
                    encoded = base64.b64encode(f.read()).decode('utf-8')
                    image_contents.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{encoded}"}
                    })
        
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": image_contents + [{"type": "text", "text": prompt}]
            }
        ]
        
        response = self.llm.create_chat_completion(
            messages=messages,
            max_tokens=512,
            temperature=0.3,
        )
        
        return response['choices'][0]['message']['content']


class VLMReasoner:
    """
    VLM reasoning layer for computer use agent.
    Combines visual detection output with VLM for action decisions.
    """
    
    def __init__(self,
                 backend: str = "ollama",
                 model: str = None,
                 model_path: str = None,
                 clip_model_path: str = None,
                 **kwargs):
        """
        Initialize VLM reasoner.
        
        Args:
            backend: "ollama" or "llamacpp"
            model: Model name for Ollama
            model_path: Path to GGUF file for llama.cpp
            clip_model_path: Path to CLIP model for llama.cpp vision
        """
        self.backend_name = backend
        self.action_history: List[str] = []
        self.last_feedback: Optional[str] = None
        
        if backend == "ollama":
            self.backend = OllamaBackend(
                model=model or "llava:7b",
                **kwargs
            )
        elif backend == "llamacpp":
            if not model_path:
                raise ValueError("model_path required for llamacpp backend")
            self.backend = LlamaCppBackend(
                model_path=model_path,
                clip_model_path=clip_model_path,
                **kwargs
            )
        else:
            raise ValueError(f"Unknown backend: {backend}")
    
    def reason(self,
               original_image: str,
               annotated_image: str,
               elements: List[Dict],
               task: str,
               include_feedback: bool = True) -> VLMResponse:
        """
        Get next action from VLM based on current screen state.
        
        Args:
            original_image: Path to original screenshot
            annotated_image: Path to annotated screenshot with element boxes
            elements: List of detected elements
            task: User task description
            include_feedback: Whether to include feedback from previous action
            
        Returns:
            VLMResponse with parsed action and metadata
        """
        start_time = time.time()
        
        # Build element list text
        element_lines = []
        for elem in elements:
            if isinstance(elem, dict):
                e_id = elem.get('id', 0)
                e_type = elem.get('type', elem.get('element_type', 'unknown'))
                e_center = elem.get('center', (0, 0))
                e_text = elem.get('text', '')
            else:
                e_id = elem.id
                e_type = elem.element_type
                e_center = elem.center
                e_text = elem.text
            
            if e_text:
                element_lines.append(f"[{e_id}] {e_type} at {tuple(e_center)} - \"{e_text[:30]}\"")
            else:
                element_lines.append(f"[{e_id}] {e_type} at {tuple(e_center)}")
        
        element_list = "\n".join(element_lines)
        
        # Build prompt
        prompt = build_task_prompt(
            element_list=element_list,
            task=task,
            action_history=self.action_history[-5:] if self.action_history else None
        )
        
        # Add feedback if available
        if include_feedback and self.last_feedback:
            prompt += "\n\n" + self.last_feedback
        
        # Generate response
        raw_response = self.backend.generate(
            prompt=prompt,
            images=[original_image, annotated_image]
        )
        
        inference_time = time.time() - start_time
        
        # Parse action
        action = parse_action(raw_response)
        
        # Extract reasoning (everything before ACTION:)
        reasoning = raw_response.split('ACTION:')[0].strip() if 'ACTION:' in raw_response else raw_response
        
        return VLMResponse(
            raw_response=raw_response,
            action=action,
            reasoning=reasoning,
            inference_time=inference_time
        )
    
    def add_action_to_history(self, action_str: str):
        """Add an executed action to history."""
        self.action_history.append(action_str)
        # Keep last 10 actions
        if len(self.action_history) > 10:
            self.action_history = self.action_history[-10:]
    
    def set_feedback(self, feedback: str):
        """Set feedback for next reasoning call."""
        self.last_feedback = feedback
    
    def clear_history(self):
        """Clear action history and feedback."""
        self.action_history = []
        self.last_feedback = None


def create_reasoner(backend: str = "ollama", **kwargs) -> VLMReasoner:
    """
    Factory function to create VLM reasoner.
    
    Examples:
        # Ollama
        reasoner = create_reasoner("ollama", model="llava:7b")
        
        # llama.cpp
        reasoner = create_reasoner("llamacpp", 
                                   model_path="models/llava.gguf",
                                   clip_model_path="models/mmproj.gguf")
    """
    return VLMReasoner(backend=backend, **kwargs)


if __name__ == "__main__":
    print("VLM Reasoner Module")
    print("Use create_reasoner() to initialize with your preferred backend.")
    
    # Test prompt parsing
    from prompts import parse_action
    
    test_responses = [
        "Looking at the screen, I can see a search input. ACTION: click 1",
        "I'll type the search query. ACTION: type \"hello world\"",
        "Need to scroll to see more. ACTION: scroll down",
    ]
    
    print("\nTest action parsing:")
    for resp in test_responses:
        print(f"  Response: {resp[:40]}...")
        print(f"  Parsed: {parse_action(resp)}")
        print()
