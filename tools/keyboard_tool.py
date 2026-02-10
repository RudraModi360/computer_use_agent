"""Keyboard Tool - Direct keyboard input."""
import pyautogui
import time
from typing import Optional, List
from .base_tool import BaseTool, ToolResult

# Configure pyautogui
pyautogui.PAUSE = 0.05
pyautogui.FAILSAFE = True


class KeyboardTool(BaseTool):
    """
    Direct keyboard control.
    Use for: typing text, pressing keys, keyboard shortcuts.
    """
    
    name = "keyboard"
    description = "Type text or press keys. Use when app is focused. Actions: type, press, hotkey"
    
    # Key mappings
    KEY_MAP = {
        'enter': 'return', 'return': 'return',
        'tab': 'tab', 'escape': 'escape', 'esc': 'escape',
        'backspace': 'backspace', 'delete': 'delete',
        'up': 'up', 'down': 'down', 'left': 'left', 'right': 'right',
        'space': 'space', 'home': 'home', 'end': 'end',
        'pageup': 'pageup', 'pagedown': 'pagedown',
        'ctrl': 'ctrl', 'alt': 'alt', 'shift': 'shift', 'win': 'win',
    }
    
    def execute(self, action: str, text: str = None, key: str = None, 
                keys: List[str] = None, interval: float = 0.02) -> ToolResult:
        """
        Execute keyboard action.
        
        Args:
            action: "type", "press", or "hotkey"
            text: Text to type (for action="type")
            key: Key to press (for action="press")
            keys: List of keys for hotkey (for action="hotkey")
            interval: Delay between keystrokes
        """
        start_time = time.time()
        
        try:
            if action == "type":
                if not text:
                    return ToolResult(False, None, "No text provided for type action")
                
                # Use write for unicode support, typewrite for ASCII
                if text.isascii():
                    pyautogui.typewrite(text, interval=interval)
                else:
                    pyautogui.write(text)
                
                return ToolResult(
                    success=True,
                    output=f"Typed: '{text[:50]}{'...' if len(text) > 50 else ''}'",
                    execution_time=time.time() - start_time
                )
            
            elif action == "press":
                if not key:
                    return ToolResult(False, None, "No key provided for press action")
                
                mapped_key = self.KEY_MAP.get(key.lower(), key.lower())
                pyautogui.press(mapped_key)
                
                return ToolResult(
                    success=True,
                    output=f"Pressed: {key}",
                    execution_time=time.time() - start_time
                )
            
            elif action == "hotkey":
                if not keys:
                    return ToolResult(False, None, "No keys provided for hotkey action")
                
                mapped_keys = [self.KEY_MAP.get(k.lower(), k.lower()) for k in keys]
                pyautogui.hotkey(*mapped_keys)
                
                return ToolResult(
                    success=True,
                    output=f"Hotkey: {'+'.join(keys)}",
                    execution_time=time.time() - start_time
                )
            
            else:
                return ToolResult(False, None, f"Unknown action: {action}")
                
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
                execution_time=time.time() - start_time
            )
    
    def get_schema(self):
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "action": {"type": "string", "enum": ["type", "press", "hotkey"], "required": True},
                "text": {"type": "string", "description": "Text to type"},
                "key": {"type": "string", "description": "Key to press"},
                "keys": {"type": "array", "description": "Keys for hotkey (e.g., ['ctrl', 's'])"}
            }
        }
