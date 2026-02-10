"""Agent Memory - State persistence across steps."""
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict


@dataclass
class ActionRecord:
    """Record of a single action."""
    step: int
    tool: str
    params: Dict
    result_success: bool
    result_output: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass 
class ScreenState:
    """Current screen state."""
    screenshot_path: Optional[str] = None
    active_app: Optional[str] = None
    detected_elements: List[Dict] = field(default_factory=list)
    element_count: int = 0


class AgentMemory:
    """
    Persistent memory for the agent across steps.
    Tracks: action history, screen state, task progress, context.
    """
    
    def __init__(self, persist_path: str = None):
        self.persist_path = persist_path
        
        # Current state
        self.current_step: int = 0
        self.task: str = ""
        self.task_started: str = datetime.now().isoformat()
        
        # History
        self.action_history: List[ActionRecord] = []
        self.screen_states: List[ScreenState] = []
        
        # Context
        self.active_app: Optional[str] = None
        self.last_action_success: bool = True
        self.accumulated_context: List[str] = []
        
        # Task tracking
        self.goals_completed: List[str] = []
        self.current_focus: str = ""
        
    def set_task(self, task: str):
        """Set the current task."""
        self.task = task
        self.task_started = datetime.now().isoformat()
        self.current_step = 0
        self.accumulated_context = [f"Task: {task}"]
    
    def record_action(self, tool: str, params: Dict, result) -> ActionRecord:
        """Record an executed action."""
        self.current_step += 1
        
        record = ActionRecord(
            step=self.current_step,
            tool=tool,
            params=params,
            result_success=result.success if hasattr(result, 'success') else bool(result),
            result_output=str(result.output if hasattr(result, 'output') else result)[:200]
        )
        
        self.action_history.append(record)
        self.last_action_success = record.result_success
        
        # Update context
        status = "✓" if record.result_success else "✗"
        self.accumulated_context.append(f"Step {self.current_step}: {tool} -> {status}")
        
        # Detect app from command
        if tool == "run_command" and record.result_success:
            cmd = params.get('command', '').lower()
            if 'notepad' in cmd:
                self.active_app = "Notepad"
            elif 'chrome' in cmd or 'browser' in cmd:
                self.active_app = "Browser"
            elif 'code' in cmd or 'vscode' in cmd:
                self.active_app = "VS Code"
        
        return record
    
    def record_screen_state(self, screenshot_path: str = None, 
                           elements: List[Dict] = None):
        """Record current screen state."""
        state = ScreenState(
            screenshot_path=screenshot_path,
            active_app=self.active_app,
            detected_elements=elements or [],
            element_count=len(elements) if elements else 0
        )
        self.screen_states.append(state)
        
        # Keep only last 5 screen states
        if len(self.screen_states) > 5:
            self.screen_states = self.screen_states[-5:]
    
    def mark_goal_completed(self, goal: str):
        """Mark a sub-goal as completed."""
        self.goals_completed.append(goal)
        self.accumulated_context.append(f"✓ Completed: {goal}")
    
    def set_focus(self, focus: str):
        """Set current focus/sub-goal."""
        self.current_focus = focus
    
    def get_context_for_vlm(self, max_history: int = 5) -> str:
        """
        Build context string for VLM prompt.
        Includes relevant history, current state, and task progress.
        """
        lines = []
        
        # Task
        lines.append(f"TASK: {self.task}")
        lines.append("")
        
        # Current state
        lines.append("CURRENT STATE:")
        lines.append(f"  Step: {self.current_step}")
        if self.active_app:
            lines.append(f"  Active App: {self.active_app}")
        if self.current_focus:
            lines.append(f"  Current Focus: {self.current_focus}")
        lines.append(f"  Last Action: {'Success' if self.last_action_success else 'Failed'}")
        lines.append("")
        
        # Recent actions
        if self.action_history:
            lines.append(f"RECENT ACTIONS (last {min(max_history, len(self.action_history))}):")
            for record in self.action_history[-max_history:]:
                status = "✓" if record.result_success else "✗"
                params_str = json.dumps(record.params)[:50]
                lines.append(f"  {record.step}. {record.tool}({params_str}) -> {status}")
            lines.append("")
        
        # Progress
        if self.goals_completed:
            lines.append("COMPLETED GOALS:")
            for goal in self.goals_completed:
                lines.append(f"  ✓ {goal}")
            lines.append("")
        
        # Last screen info
        if self.screen_states:
            last_screen = self.screen_states[-1]
            lines.append(f"LAST SCREEN: {last_screen.element_count} UI elements detected")
        
        return "\n".join(lines)
    
    def get_action_summary(self) -> str:
        """Get summary of all actions taken."""
        if not self.action_history:
            return "No actions taken yet"
        
        lines = [f"Task: {self.task}", f"Steps: {len(self.action_history)}", ""]
        
        for record in self.action_history:
            status = "✓" if record.result_success else "✗"
            lines.append(f"  {record.step}. [{status}] {record.tool}: {record.result_output[:50]}")
        
        if self.goals_completed:
            lines.append("")
            lines.append("Completed: " + ", ".join(self.goals_completed))
        
        return "\n".join(lines)
    
    def should_retry(self) -> bool:
        """Check if last action should be retried."""
        return not self.last_action_success
    
    def clear(self):
        """Clear all memory."""
        self.current_step = 0
        self.task = ""
        self.action_history = []
        self.screen_states = []
        self.active_app = None
        self.last_action_success = True
        self.accumulated_context = []
        self.goals_completed = []
        self.current_focus = ""
    
    def save(self, path: str = None):
        """Save memory to file."""
        save_path = path or self.persist_path
        if not save_path:
            return
        
        data = {
            "task": self.task,
            "task_started": self.task_started,
            "current_step": self.current_step,
            "active_app": self.active_app,
            "goals_completed": self.goals_completed,
            "action_history": [asdict(a) for a in self.action_history]
        }
        
        with open(save_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def load(self, path: str = None):
        """Load memory from file."""
        load_path = path or self.persist_path
        if not load_path or not os.path.exists(load_path):
            return
        
        with open(load_path, 'r') as f:
            data = json.load(f)
        
        self.task = data.get("task", "")
        self.task_started = data.get("task_started", "")
        self.current_step = data.get("current_step", 0)
        self.active_app = data.get("active_app")
        self.goals_completed = data.get("goals_completed", [])
