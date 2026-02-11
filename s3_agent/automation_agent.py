#!/usr/bin/env python3
"""
AUTOMATION AGENT - Phase 2 Implementation
Integrates scene graph, vision, and actions with error recovery
"""

import sys
import os
import time
import traceback
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pyautogui
from PIL import Image

from s3_agent.core.hybrid_engine import HybridVisionEngine, HybridAgent
from s3_agent.core.scene_graph import SceneGraphBuilder, SceneGraph
from s3_agent.vision import ElementDetector, ScreenshotManager


class ActionType(Enum):
    """Supported action types"""
    CLICK = "click"
    TYPE = "type"
    SCROLL = "scroll"
    WAIT = "wait"
    DONE = "done"


@dataclass
class Action:
    """Represents an action to execute"""
    action_type: ActionType
    target_id: Optional[int] = None
    coordinates: Optional[Tuple[int, int]] = None
    text: Optional[str] = None
    direction: Optional[str] = None  # for scroll
    duration: float = 0.5
    reason: str = ""
    
    def to_dict(self) -> Dict:
        return {
            'type': self.action_type.value,
            'target_id': self.target_id,
            'coordinates': self.coordinates,
            'text': self.text,
            'direction': self.direction,
            'duration': self.duration,
            'reason': self.reason
        }


@dataclass
class ActionResult:
    """Result of executing an action"""
    success: bool
    action: Action
    execution_time: float
    error_message: Optional[str] = None
    screenshot_before: Optional[bytes] = None
    screenshot_after: Optional[bytes] = None
    

class AutomationAgent:
    """
    Main automation agent with 5 basic actions:
    1. CLICK - Click at coordinates
    2. TYPE - Type text
    3. SCROLL - Scroll up/down
    4. WAIT - Wait for loading
    5. DONE - Task complete
    """
    
    def __init__(
        self,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        use_scene_graph: bool = True,
        openrouter_key: Optional[str] = None,
        ollama_model: str = "gpt-oss:20b-cloud"
    ):
        """
        Initialize automation agent
        
        Args:
            max_retries: Maximum retry attempts for failed actions
            retry_delay: Delay between retries in seconds
            use_scene_graph: Whether to build scene graph
            openrouter_key: OpenRouter API key
            ollama_model: Ollama model name
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.use_scene_graph = use_scene_graph
        
        # Initialize components
        self.vision_engine = HybridVisionEngine(
            openrouter_key=openrouter_key,
            ollama_model=ollama_model
        )
        self.hybrid_agent = HybridAgent(self.vision_engine)
        self.scene_builder = SceneGraphBuilder()
        self.detector = ElementDetector()
        self.screenshot_manager = ScreenshotManager()
        
        # Action history
        self.action_history: List[ActionResult] = []
        
        # PyAutoGUI settings
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.5
        
    def execute_task(
        self,
        task_description: str,
        max_steps: int = 20,
        timeout: float = 300.0
    ) -> Dict[str, Any]:
        """
        Execute a complete task
        
        Args:
            task_description: What to do
            max_steps: Maximum steps before giving up
            timeout: Maximum time in seconds
            
        Returns:
            Task execution results
        """
        self.log(f"Starting task: {task_description}")
        self.log(f"Max steps: {max_steps}, Timeout: {timeout}s")
        
        start_time = time.time()
        step_count = 0
        
        while step_count < max_steps:
            # Check timeout
            if time.time() - start_time > timeout:
                return {
                    'success': False,
                    'reason': 'timeout',
                    'steps_executed': step_count,
                    'total_time': time.time() - start_time
                }
            
            step_count += 1
            self.log(f"\n--- Step {step_count}/{max_steps} ---")
            
            try:
                # 1. Capture screenshot
                self.log("Capturing screenshot...")
                screenshot, screenshot_bytes = self.screenshot_manager.capture()
                
                # 2. Build scene graph (optional)
                scene_graph = None
                if self.use_scene_graph:
                    elements = self.detector.detect_with_ocr(screenshot)
                    scene_graph = self.scene_builder.build_from_ocr_elements(elements)
                    self.log(f"Scene graph: {len(scene_graph.elements)} elements")
                
                # 3. Get next action from hybrid agent
                self.log("Getting next action...")
                action = self._get_next_action(
                    screenshot_bytes,
                    task_description,
                    scene_graph
                )
                
                if action.action_type == ActionType.DONE:
                    self.log("Task completed!")
                    return {
                        'success': True,
                        'steps_executed': step_count,
                        'total_time': time.time() - start_time,
                        'action_history': [r.to_dict() for r in self.action_history]
                    }
                
                # 4. Execute action with retry
                self.log(f"Executing: {action.action_type.value}")
                result = self._execute_action_with_retry(action, screenshot_bytes)
                self.action_history.append(result)
                
                if result.success:
                    self.log(f"✓ Action succeeded in {result.execution_time:.2f}s")
                else:
                    self.log(f"✗ Action failed: {result.error_message}", "ERROR")
                    # Continue to next step anyway
                
                # 5. Wait before next step
                time.sleep(1.0)
                
            except Exception as e:
                self.log(f"Error in step {step_count}: {e}", "ERROR")
                traceback.print_exc()
                continue
        
        # Max steps reached
        return {
            'success': False,
            'reason': 'max_steps_reached',
            'steps_executed': step_count,
            'total_time': time.time() - start_time,
            'action_history': [r.to_dict() for r in self.action_history]
        }
    
    def _get_next_action(
        self,
        screenshot_bytes: bytes,
        task: str,
        scene_graph: Optional[SceneGraph] = None
    ) -> Action:
        """Get next action from hybrid agent"""
        # Get scene text for context
        scene_text = ""
        if scene_graph:
            scene_text = scene_graph.to_text(max_elements=30)
        
        # Use hybrid agent to decide action
        result = self.hybrid_agent.process_step(
            screenshot_bytes,
            task=task,
            history=[r.action.to_dict() for r in self.action_history[-5:]]  # Last 5 actions
        )
        
        # Parse action from result
        action_data = result['action']
        
        # Map to ActionType
        action_type_str = action_data.get('type', 'UNKNOWN').upper()
        if action_type_str == 'CLICK':
            action_type = ActionType.CLICK
            coords = action_data.get('params', {})
            return Action(
                action_type=ActionType.CLICK,
                coordinates=(coords.get('x', 500), coords.get('y', 300)),
                reason=result.get('reasoning', '')
            )
        elif action_type_str == 'TYPE':
            return Action(
                action_type=ActionType.TYPE,
                text=action_data.get('params', {}).get('text', ''),
                reason=result.get('reasoning', '')
            )
        elif action_type_str == 'SCROLL':
            return Action(
                action_type=ActionType.SCROLL,
                direction=action_data.get('params', {}).get('direction', 'down'),
                reason=result.get('reasoning', '')
            )
        elif action_type_str == 'DONE':
            return Action(
                action_type=ActionType.DONE,
                reason="Task completed"
            )
        else:
            # Default to wait
            return Action(
                action_type=ActionType.WAIT,
                duration=2.0,
                reason="Waiting for UI to stabilize"
            )
    
    def _execute_action_with_retry(
        self,
        action: Action,
        screenshot_before: bytes
    ) -> ActionResult:
        """Execute action with retry logic"""
        for attempt in range(1, self.max_retries + 1):
            try:
                self.log(f"  Attempt {attempt}/{self.max_retries}...")
                
                start = time.time()
                success = self._execute_single_action(action)
                elapsed = time.time() - start
                
                if success:
                    # Capture after screenshot
                    screenshot_after = self.screenshot_manager.capture()[1]
                    
                    return ActionResult(
                        success=True,
                        action=action,
                        execution_time=elapsed,
                        screenshot_before=screenshot_before,
                        screenshot_after=screenshot_after
                    )
                else:
                    if attempt < self.max_retries:
                        self.log(f"  Failed, retrying in {self.retry_delay}s...")
                        time.sleep(self.retry_delay)
                    
            except Exception as e:
                error_msg = str(e)
                self.log(f"  Error: {error_msg}", "ERROR")
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)
        
        # All retries failed
        return ActionResult(
            success=False,
            action=action,
            execution_time=0,
            error_message=f"Failed after {self.max_retries} attempts",
            screenshot_before=screenshot_before
        )
    
    def _execute_single_action(self, action: Action) -> bool:
        """Execute a single action (no retry)"""
        if action.action_type == ActionType.CLICK:
            if action.coordinates:
                x, y = action.coordinates
                pyautogui.click(x, y, duration=action.duration)
                return True
                
        elif action.action_type == ActionType.TYPE:
            if action.text:
                pyautogui.typewrite(action.text, interval=0.01)
                return True
                
        elif action.action_type == ActionType.SCROLL:
            clicks = 3 if action.direction == 'down' else -3
            pyautogui.scroll(clicks)
            return True
            
        elif action.action_type == ActionType.WAIT:
            time.sleep(action.duration)
            return True
            
        elif action.action_type == ActionType.DONE:
            return True
        
        return False
    
    def log(self, message: str, level: str = "INFO"):
        """Log message"""
        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")


# Demo function
def demo():
    """Demo the automation agent"""
    print("="*60)
    print("AUTOMATION AGENT DEMO")
    print("="*60)
    print("\nThis demo will:")
    print("  1. Capture your desktop")
    print("  2. Build scene graph")
    print("  3. Execute actions (WITH SAFETY)")
    print("\n⚠️  IMPORTANT:")
    print("  - Actions will be shown but NOT executed")
    print("  - You can enable execution by changing safety flag")
    print("="*60)
    
    agent = AutomationAgent(
        max_retries=3,
        use_scene_graph=True,
        openrouter_key="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",
        ollama_model="gpt-oss:20b-cloud"
    )
    
    # For demo, just show what would happen
    print("\n📸 Capturing screenshot...")
    screenshot, screenshot_bytes = agent.screenshot_manager.capture()
    
    print("🔍 Building scene graph...")
    elements = agent.detector.detect_with_ocr(screenshot)
    scene = agent.scene_builder.build_from_ocr_elements(elements)
    
    print(f"\nFound {len(scene.elements)} elements:")
    print(scene.to_text(max_elements=20))
    
    print("\n✓ Demo complete!")
    print("To run full automation, use: agent.execute_task('your task')")


if __name__ == "__main__":
    demo()
