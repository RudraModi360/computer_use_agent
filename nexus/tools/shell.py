
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
        return shell.execute(command, timeout=config.SHELL_TIMEOUT)
    except Exception as e:
        return f"Error executing shell command: {e}"
