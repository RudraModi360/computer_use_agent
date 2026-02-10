"""
Smart Agent - Tool-based orchestrator with memory.
Main entry point for the enhanced computer use agent.
"""

import os
import time
import base64
from typing import Dict, List, Optional, Union
from dataclasses import dataclass

try:
    import ollama
except ImportError:
    ollama = None

try:
    from llama_cpp import Llama
    from llama_cpp.llama_chat_format import Llava15ChatHandler
except ImportError:
    Llama = None
    Llava15ChatHandler = None

from tools import CommandTool, KeyboardTool, VisionTool, ScreenTool, WaitTool, ToolResult
from memory import AgentMemory
from tool_prompts import TOOL_CALLING_SYSTEM, build_tool_prompt, parse_tool_call


@dataclass
class StepResult:
    """Result of a single agent step."""
    step: int
    tool: str
    params: Dict
    success: bool
    output: str
    elapsed: float


class SmartAgent:
    """
    Tool-based computer use agent with memory.
    
    Uses a VLM to decide which tool to use, then executes it.
    Much faster than pure UI navigation.
    """
    
    def __init__(self,
                 vlm_backend: str = "ollama",
                 vlm_model: str = "qwen3:0.6b",
                 vlm_host: str = "http://localhost:11434",
                 model_path: str = None,
                 clip_model_path: str = None,
                 output_dir: str = "agent_output",
                 max_retries: int = 2):
        """
        Initialize smart agent.
        
        Args:
            vlm_backend: "ollama" or "llamacpp"
            vlm_model: Model name for Ollama
            vlm_host: Ollama API host (if using ollama)
            model_path: Path to GGUF model (if using llamacpp)
            clip_model_path: Path to mmproj GGUF for vision (if using llamacpp)
            output_dir: Directory for screenshots
            max_retries: Max retries per action
        """
        self.vlm_backend = vlm_backend
        self.vlm_model = vlm_model
        self.vlm_host = vlm_host
        self.output_dir = output_dir
        self.max_retries = max_retries
        
        # Initialize llama-cpp model if specified
        self.llm = None
        if vlm_backend == "llamacpp":
            if Llama is None:
                raise ImportError("llama-cpp-python is not installed. Install with: pip install llama-cpp-python")
            if not model_path:
                raise ValueError("model_path is required for llamacpp backend")
            
            print(f"📦 Loading llama.cpp model: {model_path}")
            if clip_model_path:
                chat_handler = Llava15ChatHandler(clip_model_path=clip_model_path)
                self.llm = Llama(model_path=model_path, chat_handler=chat_handler, n_ctx=2048, n_gpu_layers=-1)
            else:
                self.llm = Llama(model_path=model_path, n_ctx=2048, n_gpu_layers=-1)
        
        os.makedirs(output_dir, exist_ok=True)
        
        # Initialize tools
        print("🔧 Initializing Smart Agent...")
        self.tools: Dict[str, any] = {
            "run_command": CommandTool(),
            "keyboard": KeyboardTool(),
            "computer_use": VisionTool(output_dir=output_dir),
            "read_screen": ScreenTool(output_dir=output_dir),
            "wait": WaitTool(),
        }
        
        # Initialize memory
        self.memory = AgentMemory()
        
        # Step tracking
        self.step_results: List[StepResult] = []
        
        print("✅ Smart Agent initialized")
        print(f"   Model: {vlm_model}")
        print(f"   Tools: {list(self.tools.keys())}")
    
    def run(self, task: str, max_steps: int = 10) -> List[StepResult]:
        """
        Execute a task using tools.
        
        Args:
            task: Natural language task description
            max_steps: Maximum steps before stopping
            
        Returns:
            List of StepResult objects
        """
        print(f"\n{'='*60}")
        print(f"🎯 TASK: {task}")
        print(f"{'='*60}\n")
        
        # Initialize memory for task
        self.memory.set_task(task)
        self.step_results = []
        
        # Initial screen capture to ground the agent
        print("📸 Capturing initial screen state...")
        init_result = self.tools["computer_use"].execute(action="detect")
        if init_result.success:
            meta = init_result.metadata or {}
            self.memory.record_screen_state(
                screenshot_path=meta.get('screenshot_path'),
                elements=meta.get('elements', [])
            )
        
        for step in range(max_steps):
            print(f"\n--- Step {step + 1}/{max_steps} ---")
            step_start = time.time()
            
            try:
                # 1. Get context from memory
                context = self.memory.get_context_for_vlm()
                
                # 2. Ask VLM which tool to use
                print("🧠 Deciding next action...")
                tool_call = self._get_tool_decision(context)
                
                tool_name = tool_call.get('tool')
                params = tool_call.get('params', {})
                
                print(f"   Tool: {tool_name}")
                print(f"   Params: {params}")
                
                # 3. Check for completion
                if tool_name == 'done':
                    print("\n✅ Task marked complete by agent")
                    result = StepResult(step + 1, 'done', {}, True, "Complete", time.time() - step_start)
                    self.step_results.append(result)
                    return self.step_results
                
                # 4. Execute tool
                if tool_name and tool_name in self.tools:
                    print(f"⚡ Executing: {tool_name}")
                    tool_result = self.tools[tool_name].execute(**params)
                    print(f"   Result: {tool_result}")
                    
                    # 5. Mandatory Verification for UI-altering tools
                    # If we ran a command, keyboard, or UI action, we MUST check the screen now
                    if tool_name in ["run_command", "keyboard", "computer_use"]:
                        print("🔍 Verifying state change...")
                        # Small wait for UI to respond (e.g. windows opening)
                        time.sleep(1.0 if tool_name == "run_command" else 0.5)
                        
                        verify_result = self.tools["computer_use"].execute(action="detect")
                        if verify_result.success:
                            meta = verify_result.metadata or {}
                            self.memory.record_screen_state(
                                screenshot_path=meta.get('screenshot_path'),
                                elements=meta.get('elements', [])
                            )
                            # Update reasoning about success
                            if tool_name == "run_command":
                                # Check if a new window or app appeared (simplified)
                                tool_result.output += " (Screen updated, verifying window...)"
                    
                    # 6. Update memory
                    self.memory.record_action(tool_name, params, tool_result)
                    
                    result = StepResult(
                        step + 1,
                        tool_name,
                        params,
                        tool_result.success,
                        str(tool_result.output)[:100],
                        time.time() - step_start
                    )
                    
                else:
                    print(f"   ⚠️ Unknown tool: {tool_name}")
                    result = StepResult(step + 1, tool_name or 'unknown', params, False, 
                                       "Unknown tool", time.time() - step_start)
                
                self.step_results.append(result)
                
                # Small delay for UI to update
                time.sleep(0.3)
                
            except Exception as e:
                print(f"❌ Error: {e}")
                result = StepResult(step + 1, 'error', {}, False, str(e), time.time() - step_start)
                self.step_results.append(result)
        
        print(f"\n⚠️ Reached max steps ({max_steps})")
        return self.step_results
    
    def _get_tool_decision(self, context: str) -> Dict:
        """Get tool decision from VLM."""
        prompt = build_tool_prompt(context)
        
        # Get last screenshot for visual context
        images = []
        last_screen = self.memory.screen_states[-1] if self.memory.screen_states else None
        if last_screen and last_screen.screenshot_path:
            images.append(last_screen.screenshot_path)
        
        try:
            response = self._call_vlm(prompt, images=images)
            decision = parse_tool_call(response)
            if not decision.get('tool'):
                print(f"   ⚠️ Could not parse tool from response: {response[:100]}...")
            return decision
        except Exception as e:
            print(f"   VLM error: {e}")
            return {'tool': None, 'params': {}, 'error': str(e)}
    
    def _call_vlm(self, prompt: str, images: List[str] = None) -> str:
        """Call VLM using selected backend."""
        if self.vlm_backend == "ollama":
            return self._call_ollama_native(prompt, images)
        elif self.vlm_backend == "llamacpp":
            return self._call_llamacpp_native(prompt, images)
        else:
            raise ValueError(f"Unsupported backend: {self.vlm_backend}")

    def _call_ollama_native(self, prompt: str, images: List[str] = None) -> str:
        """Call Ollama using native python library."""
        if ollama is None:
            raise ImportError("ollama python library is not installed. Install with: pip install ollama")
        
        client = ollama.Client(host=self.vlm_host)
        
        # Add images if provided
        img_data = []
        if images:
            for img_path in images:
                if os.path.exists(img_path):
                    with open(img_path, 'rb') as f:
                        img_data.append(f.read())
        
        response = client.generate(
            model=self.vlm_model,
            prompt=prompt,
            system=TOOL_CALLING_SYSTEM,
            images=img_data if img_data else None,
            options={"temperature": 0.2}
        )
        return response.get('response', '')

    def _call_llamacpp_native(self, prompt: str, images: List[str] = None) -> str:
        """Call llama.cpp using native python library."""
        if not self.llm:
            raise RuntimeError("llama.cpp model not initialized")
        
        messages = [
            {"role": "system", "content": TOOL_CALLING_SYSTEM},
            {"role": "user", "content": []}
        ]
        
        content = []
        if images:
            for img_path in images:
                if os.path.exists(img_path):
                    with open(img_path, 'rb') as f:
                        base64_image = base64.b64encode(f.read()).decode('utf-8')
                        content.append({
                            "type": "image_url",
                            "image_url": f"data:image/jpeg;base64,{base64_image}"
                        })
        
        content.append({"type": "text", "text": prompt})
        messages[1]["content"] = content
        
        response = self.llm.create_chat_completion(
            messages=messages,
            max_tokens=256,
            temperature=0.2
        )
        return response['choices'][0]['message']['content']
    
    def get_summary(self) -> str:
        """Get summary of execution."""
        lines = [
            f"Task: {self.memory.task}",
            f"Steps: {len(self.step_results)}",
            ""
        ]
        
        total_time = sum(r.elapsed for r in self.step_results)
        lines.append(f"Total time: {total_time:.2f}s")
        lines.append("")
        
        for r in self.step_results:
            status = "✓" if r.success else "✗"
            lines.append(f"  {r.step}. [{status}] {r.tool}: {r.output[:40]}")
        
        return "\n".join(lines)


def main():
    """Demo usage."""
    print("🤖 Smart Agent Demo")
    print("="*50)
    
    # Use a small fast model for tool routing
    agent = SmartAgent(
        vlm_model="qwen3:0.6b",  # Fast model
        output_dir="agent_output"
    )
    
    # Get task from user
    task = input("Enter task (or press Enter for demo): ").strip()
    if not task:
        task = "Open Notepad and type 'Hello World'"
    
    # Run
    results = agent.run(task, max_steps=5)
    
    # Summary
    print("\n" + "="*50)
    print("📊 SUMMARY")
    print("="*50)
    print(agent.get_summary())


if __name__ == "__main__":
    main()
