from .base_tool import BaseTool, ToolResult
import time

class WaitTool(BaseTool):
    """Tool to wait for a specified duration."""
    
    name = "wait"
    description = "Wait for a specified duration (in seconds). Use when waiting for pages to load or transitions."
    
    def execute(self, seconds: float = 1.0) -> ToolResult:
        start_time = time.time()
        time.sleep(seconds)
        return ToolResult(
            success=True,
            output=f"Waited for {seconds}s",
            execution_time=time.time() - start_time
        )
