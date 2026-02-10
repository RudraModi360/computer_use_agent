"""
Action Executor Module
Executes parsed actions from VLM (click, type, scroll, etc.)
"""

import pyautogui
import time
import threading
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass

pyautogui.PAUSE = 0.1
pyautogui.FAILSAFE = True


@dataclass
class ActionResult:
    """Result of an executed action."""
    success: bool
    action_type: str
    details: str
    execution_time: float
    error: Optional[str] = None


class ActionExecutor:
    """Executes UI actions based on VLM decisions."""
    
    def __init__(self, click_duration: float = 0.1, type_interval: float = 0.02,
                 show_visual_feedback: bool = True):
        self.click_duration = click_duration
        self.type_interval = type_interval
        self.show_visual_feedback = show_visual_feedback
    
    def execute(self, action: dict, elements: List[Dict]) -> ActionResult:
        """Execute a parsed action."""
        start_time = time.time()
        action_type = action.get('type', 'unknown')
        
        handlers = {
            'click': self._click, 'type': self._type, 'scroll': self._scroll,
            'press': self._press, 'wait': self._wait, 'done': self._done
        }
        
        if action_type not in handlers:
            return ActionResult(False, action_type, f"Unknown: {action_type}", 
                              time.time() - start_time, f"Unknown action")
        
        try:
            result = handlers[action_type](action, elements)
            result.execution_time = time.time() - start_time
            return result
        except Exception as e:
            return ActionResult(False, action_type, f"Error: {e}", 
                              time.time() - start_time, str(e))
    
    def _click(self, action: dict, elements: List[Dict]) -> ActionResult:
        element_id = action.get('element_id')
        if element_id is None:
            return ActionResult(False, 'click', "No element_id", 0, "Missing element_id")
        
        target = next((e for e in elements if e.get('id') == element_id), None)
        if not target:
            return ActionResult(False, 'click', f"Element [{element_id}] not found", 0)
        
        x, y = target.get('center', (0, 0))
        if self.show_visual_feedback:
            self._highlight(x, y)
        
        pyautogui.moveTo(x, y, duration=self.click_duration)
        pyautogui.click()
        return ActionResult(True, 'click', f"Clicked [{element_id}] at ({x}, {y})", 0)
    
    def _type(self, action: dict, elements: List[Dict]) -> ActionResult:
        text = action.get('text', '')
        if not text:
            return ActionResult(False, 'type', "No text", 0, "Empty text")
        
        pyautogui.typewrite(text, interval=self.type_interval) if text.isascii() else pyautogui.write(text)
        return ActionResult(True, 'type', f"Typed: \"{text[:50]}\"", 0)
    
    def _scroll(self, action: dict, elements: List[Dict]) -> ActionResult:
        direction = action.get('direction', 'down').lower()
        amount = 3 if direction == 'up' else -3
        pyautogui.scroll(amount)
        return ActionResult(True, 'scroll', f"Scrolled {direction}", 0)
    
    def _press(self, action: dict, elements: List[Dict]) -> ActionResult:
        key = action.get('key', 'enter').lower()
        key_map = {'enter': 'return', 'esc': 'escape'}
        pyautogui.press(key_map.get(key, key))
        return ActionResult(True, 'press', f"Pressed {key}", 0)
    
    def _wait(self, action: dict, elements: List[Dict]) -> ActionResult:
        duration = action.get('duration', 1.0)
        time.sleep(duration)
        return ActionResult(True, 'wait', f"Waited {duration}s", duration)
    
    def _done(self, action: dict, elements: List[Dict]) -> ActionResult:
        return ActionResult(True, 'done', "Task complete", 0)
    
    def _highlight(self, x: int, y: int, duration: float = 0.5):
        try:
            import tkinter as tk
            def show():
                root = tk.Tk()
                root.overrideredirect(True)
                root.attributes('-topmost', True)
                root.attributes('-transparentcolor', 'white')
                root.geometry(f"60x60+{x-30}+{y-30}")
                c = tk.Canvas(root, width=60, height=60, bg='white', highlightthickness=0)
                c.pack()
                c.create_oval(5, 5, 55, 55, outline='red', width=3)
                root.after(int(duration * 1000), root.destroy)
                root.mainloop()
            threading.Thread(target=show, daemon=True).start()
        except: pass
