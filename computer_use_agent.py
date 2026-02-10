"""
Computer Use Agent - Main Orchestrator
2-Tier architecture with feedback loop for reliable computer automation.
"""

import os
import time
import pyautogui
from typing import Optional, List, Dict
from dataclasses import dataclass
from enum import Enum

from visual_detector import VisualDetector, UIElement
from annotator import Annotator
from vlm_reasoner import VLMReasoner, create_reasoner
from action_executor import ActionExecutor, ActionResult
from feedback_monitor import FeedbackMonitor, FeedbackType


class AgentState(Enum):
    IDLE = "idle"
    DETECTING = "detecting"
    REASONING = "reasoning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class StepResult:
    """Result of a single agent step."""
    step_number: int
    state: AgentState
    action: Optional[dict]
    action_result: Optional[ActionResult]
    feedback_type: Optional[FeedbackType]
    reasoning: str
    elapsed_time: float


class ComputerUseAgent:
    """
    Main orchestrator for 2-tier computer use.
    
    Architecture:
    1. Tier 1: Fast visual detection (CV + OCR)
    2. Tier 2: Lightweight VLM reasoning
    3. Feedback loop for verification and retry
    """
    
    def __init__(self,
                 vlm_backend: str = "ollama",
                 vlm_model: str = "llava:7b",
                 model_path: str = None,
                 clip_model_path: str = None,
                 max_retries: int = 2,
                 output_dir: str = "agent_output"):
        """
        Initialize computer use agent.
        
        Args:
            vlm_backend: "ollama" or "llamacpp"
            vlm_model: Model name for Ollama
            model_path: Path to GGUF model for llama.cpp
            clip_model_path: Path to CLIP model for llama.cpp
            max_retries: Max retries per action
            output_dir: Directory for screenshots and logs
        """
        self.max_retries = max_retries
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        # Initialize components
        print("🔧 Initializing Computer Use Agent...")
        
        self.detector = VisualDetector(ocr_enabled=True)
        self.annotator = Annotator()
        self.executor = ActionExecutor(show_visual_feedback=True)
        self.feedback = FeedbackMonitor()
        
        # Initialize VLM
        if vlm_backend == "ollama":
            self.vlm = create_reasoner("ollama", model=vlm_model)
        elif vlm_backend == "llamacpp":
            self.vlm = create_reasoner("llamacpp", model_path=model_path,
                                       clip_model_path=clip_model_path)
        else:
            raise ValueError(f"Unknown backend: {vlm_backend}")
        
        self.state = AgentState.IDLE
        self.current_task: Optional[str] = None
        self.step_history: List[StepResult] = []
        
        print("✅ Agent initialized")
    
    def run(self, task: str, max_steps: int = 10) -> List[StepResult]:
        """
        Execute a task using the 2-tier computer use model.
        
        Args:
            task: Natural language task description
            max_steps: Maximum steps before giving up
            
        Returns:
            List of StepResult objects documenting the execution
        """
        print(f"\n{'='*60}")
        print(f"🎯 TASK: {task}")
        print(f"{'='*60}\n")
        
        self.current_task = task
        self.step_history = []
        self.vlm.clear_history()
        self.feedback.clear_history()
        
        for step in range(max_steps):
            print(f"\n--- Step {step + 1}/{max_steps} ---")
            step_start = time.time()
            
            try:
                result = self._execute_step(step + 1, task)
                self.step_history.append(result)
                
                if result.state == AgentState.COMPLETED:
                    print(f"\n✅ Task completed in {step + 1} steps!")
                    return self.step_history
                
                if result.state == AgentState.FAILED:
                    print(f"\n❌ Task failed at step {step + 1}")
                    return self.step_history
                    
            except Exception as e:
                print(f"❌ Error in step {step + 1}: {e}")
                self.step_history.append(StepResult(
                    step + 1, AgentState.FAILED, None, None, None,
                    f"Exception: {e}", time.time() - step_start
                ))
                return self.step_history
        
        print(f"\n⚠️ Reached max steps ({max_steps}) without completion")
        return self.step_history
    
    def _execute_step(self, step_num: int, task: str) -> StepResult:
        """Execute a single step of the agent loop."""
        step_start = time.time()
        
        # 1. DETECTION
        self.state = AgentState.DETECTING
        print("📸 Capturing screenshot...")
        screenshot = pyautogui.screenshot()
        original_path = os.path.join(self.output_dir, f"step_{step_num}_original.png")
        screenshot.save(original_path)
        
        print("🔍 Detecting UI elements...")
        elements = self.detector.detect(original_path, selective_ocr=True)
        elements_dict = [e.to_dict() if hasattr(e, 'to_dict') else e for e in elements]
        
        # 2. ANNOTATION
        annotated_path = os.path.join(self.output_dir, f"step_{step_num}_annotated.png")
        self.annotator.annotate(original_path, elements_dict, annotated_path)
        
        # Capture baseline for feedback
        self.feedback.capture_baseline()
        
        # 3. VLM REASONING
        self.state = AgentState.REASONING
        print("🧠 VLM reasoning...")
        vlm_response = self.vlm.reason(
            original_image=original_path,
            annotated_image=annotated_path,
            elements=elements_dict,
            task=task
        )
        
        action = vlm_response.action
        print(f"   Reasoning: {vlm_response.reasoning[:100]}...")
        print(f"   Action: {action}")
        print(f"   Inference time: {vlm_response.inference_time:.2f}s")
        
        # Check for completion
        if action.get('type') == 'done':
            self.state = AgentState.COMPLETED
            return StepResult(step_num, AgentState.COMPLETED, action, None, None,
                            vlm_response.reasoning, time.time() - step_start)
        
        # 4. EXECUTION
        self.state = AgentState.EXECUTING
        print(f"⚡ Executing: {action.get('type')}")
        action_result = self.executor.execute(action, elements_dict)
        print(f"   Result: {action_result.details}")
        
        # 5. VERIFICATION
        self.state = AgentState.VERIFYING
        print("🔍 Verifying...")
        screen_change = self.feedback.detect_changes()
        feedback_result = self.feedback.analyze_action_result(action, action_result, screen_change)
        
        print(f"   Feedback: {feedback_result.feedback_type.value}")
        print(f"   {feedback_result.details}")
        
        # Handle retry if needed
        if self.feedback.should_retry(feedback_result):
            retry_count = 0
            while retry_count < self.max_retries:
                retry_count += 1
                print(f"   🔄 Retry {retry_count}/{self.max_retries}")
                
                # Re-detect and re-execute
                elements = self.detector.detect(original_path)
                action_result = self.executor.execute(action, 
                    [e.to_dict() if hasattr(e, 'to_dict') else e for e in elements])
                
                screen_change = self.feedback.detect_changes()
                feedback_result = self.feedback.analyze_action_result(action, action_result, screen_change)
                
                if not self.feedback.should_retry(feedback_result):
                    break
        
        # Update VLM with feedback for next step
        feedback_text = f"Last action: {action.get('type')}\n"
        feedback_text += f"Result: {feedback_result.feedback_type.value}\n"
        feedback_text += f"Details: {feedback_result.details}"
        self.vlm.set_feedback(feedback_text)
        self.vlm.add_action_to_history(f"{action.get('type')} -> {feedback_result.feedback_type.value}")
        
        return StepResult(
            step_num, AgentState.VERIFYING, action, action_result,
            feedback_result.feedback_type, vlm_response.reasoning,
            time.time() - step_start
        )
    
    def get_summary(self) -> str:
        """Get execution summary."""
        if not self.step_history:
            return "No steps executed"
        
        lines = [f"Task: {self.current_task}", f"Steps: {len(self.step_history)}", ""]
        
        total_time = sum(s.elapsed_time for s in self.step_history)
        lines.append(f"Total time: {total_time:.2f}s")
        
        for step in self.step_history:
            action_str = step.action.get('type', '?') if step.action else '-'
            fb = step.feedback_type.value if step.feedback_type else '-'
            lines.append(f"  Step {step.step_number}: {action_str} -> {fb} ({step.elapsed_time:.2f}s)")
        
        return "\n".join(lines)


def main():
    """Example usage."""
    print("🤖 2-Tier Computer Use Agent")
    print("="*50)
    
    # Initialize with Ollama (default)
    agent = ComputerUseAgent(
        vlm_backend="ollama",
        vlm_model="llava:7b",
        max_retries=2,
        output_dir="agent_output"
    )
    
    # Example task
    task = input("Enter task (or press Enter for demo): ").strip()
    if not task:
        task = "Open the Start menu and search for Notepad"
    
    # Run
    results = agent.run(task, max_steps=5)
    
    # Summary
    print("\n" + "="*50)
    print("📊 EXECUTION SUMMARY")
    print("="*50)
    print(agent.get_summary())


if __name__ == "__main__":
    main()
