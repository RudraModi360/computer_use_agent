"""Command Tool - Execute shell commands."""
import subprocess
import time
from typing import Optional
from .base_tool import BaseTool, ToolResult


class CommandTool(BaseTool):
    """
    Execute shell commands.
    Use for: opening applications, running scripts, file operations.
    """
    
    name = "run_command"
    description = "Execute a shell command. Use for opening apps (notepad.exe), running scripts, file operations."
    
    def __init__(self, timeout: int = 30, shell: bool = True):
        self.timeout = timeout
        self.shell = shell
    
    def execute(self, command: str, wait: bool = False, timeout: Optional[int] = None) -> ToolResult:
        """
        Execute a shell command.
        
        Args:
            command: The command to execute
            wait: Whether to wait for command completion
            timeout: Override default timeout
        """
        start_time = time.time()
        
        try:
            if wait:
                # Wait for completion
                result = subprocess.run(
                    command,
                    shell=self.shell,
                    capture_output=True,
                    text=True,
                    timeout=timeout or self.timeout
                )
                output = result.stdout or result.stderr
                success = result.returncode == 0
            else:
                # Start and don't wait (for apps like notepad)
                process = subprocess.Popen(
                    command,
                    shell=self.shell,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                # Give it a moment to start
                time.sleep(0.5)
                
                # Check if it crashed immediately
                poll = process.poll()
                if poll is not None and poll != 0:
                    success = False
                    output = f"Process exited with code {poll}"
                else:
                    success = True
                    output = f"Started: {command} (PID: {process.pid})"
            
            return ToolResult(
                success=success,
                output=output,
                execution_time=time.time() - start_time,
                metadata={"command": command}
            )
            
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                output=None,
                error=f"Command timed out after {timeout or self.timeout}s",
                execution_time=time.time() - start_time
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
                "command": {"type": "string", "description": "Shell command to execute", "required": True},
                "wait": {"type": "boolean", "description": "Wait for completion", "default": False}
            }
        }
