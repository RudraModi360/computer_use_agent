
from typing import Dict, Any
from nexus.utils.shell_manager import ShellManager
from nexus.config import config

# Singleton Manager (shared across tool calls)
_shell_manager = ShellManager()

def run_shell(command: str) -> str:
    """
    Execute a Windows shell command using the visible Satellite Shell.
    Use this for system tasks, file operations (dir, type), and exploration.
    
    Args:
        command (str): The command line string to execute (e.g. 'dir /w', 'echo hello > test.txt')
    
    Returns:
        str: The standard output and error from the command.
    """
    try:
        shell = _shell_manager.get_available_shell()
        
        # Explicit Feedback for User (as requested)
        print(f"\n[Shell] Executing: {command}")
        
        result = shell.execute(command, timeout=config.SHELL_TIMEOUT)
        
        # Show output in main terminal for cross-reference
        if result.strip():
            print(f"[Shell] Output:\n{result}\n")
        else:
            print("[Shell] (No Output)")
            
        return result
    except Exception as e:
        error_msg = f"Error executing shell command: {e}"
        print(f"[Shell] {error_msg}")
        return error_msg
