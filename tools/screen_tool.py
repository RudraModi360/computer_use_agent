"""Screen Tool - Read current screen state."""
import pyautogui
import time
import os
from typing import Optional
from .base_tool import BaseTool, ToolResult


class ScreenTool(BaseTool):
    """
    Capture and read screen state.
    Use for: getting current screen state, checking what's visible.
    """
    
    name = "read_screen"
    description = "Capture screenshot and describe current screen state. Use to understand what's visible."
    
    def __init__(self, output_dir: str = "agent_output"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self._screenshot_counter = 0
    
    def execute(self, save: bool = True, region: tuple = None) -> ToolResult:
        """
        Capture current screen.
        
        Args:
            save: Whether to save screenshot to file
            region: Optional (x, y, width, height) to capture specific region
        """
        start_time = time.time()
        
        try:
            if region:
                screenshot = pyautogui.screenshot(region=region)
            else:
                screenshot = pyautogui.screenshot()
            
            path = None
            if save:
                self._screenshot_counter += 1
                path = os.path.join(self.output_dir, f"screen_{self._screenshot_counter}.png")
                screenshot.save(path)
            
            # Get basic info
            width, height = screenshot.size
            
            return ToolResult(
                success=True,
                output={
                    "path": path,
                    "width": width,
                    "height": height,
                    "region": region
                },
                execution_time=time.time() - start_time,
                metadata={"screenshot_path": path}
            )
            
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
                "save": {"type": "boolean", "default": True},
                "region": {"type": "array", "description": "[x, y, width, height]"}
            }
        }
