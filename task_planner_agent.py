import asyncio,os,sys
from agentry.agents import Agent
from s3_agent.utils.shell_manager import ShellManager
from s3_agent.automation_agent import AutomationAgent

# 1. Initialize Shell Manager
shell_manager = ShellManager()

def run_term_command(cmd: str) -> str:
    """
    Executes a system command in a visible, managed shell window.
    
    Use this tool for:
    - Listing files (dir)
    - Searching text (find, findstr)
    - Checking network (ipconfig, ping)
    - Getting system info (whoami, systeminfo)
    - Reading files (type)
    
    Args:
        cmd: The command execution string (e.g., "dir /o:-d", "ipconfig").
    
    Returns:
        The text output from the command execution.
    """
    print(f"[Tool] Executing: {cmd}")
    try:
        shell = shell_manager.get_available_shell()
        output = shell.execute(cmd)
        
        # Auto-recovery logic
        if "Connection lost" in output or "Error communicating" in output:
             print("[Tool] Shell connection lost, spawning new shell...")
             shell_manager._sync_shells() # Cleanup
             shell = shell_manager.get_available_shell() # New
             output = shell.execute(cmd)
             
        # Log minimal output for debug (truncate large outputs)
        preview = output[:200] + "..." if len(output) > 200 else output
        print(f"[Tool Output] {preview}")
        return output
        
    except Exception as e:
        return f"Error executing command: {e}"

def perform_gui_action(gui_task: str) -> str:
    """
    Executes a GUI-based task by analyzing the screen and performing mouse/keyboard actions.
    
    Use this tool for:
    - Clicking buttons or links in a GUI application.
    - Typing into input fields or text editors.
    - Scrolling through pages or lists.
    - Any task that requires visual interaction with the screen.
    
    Args:
        gui_task: A natural language description of what to do on the screen (e.g., "Click the 'File' menu in Notepad", "Type 'Hello' into the search bar").
    
    Returns:
        A summary of the actions performed and whether the task was successful.
    """
    print(f"[Tool] Performing GUI Task: {gui_task}")
    try:
        # Initialize AutomationAgent (it will use env keys for Groq/Ollama)
        agent = AutomationAgent(
            max_retries=3,
            use_scene_graph=True
        )
        
        # Execute the task
        result = agent.execute_task(gui_task, max_steps=10)
        
        if result['success']:
            summary = f"GUI Task succeeded: {gui_task}.\n"
            if 'final_result' in result:
                summary += f"Result/Observation: {result['final_result']}"
            return summary
        else:
            return f"GUI Task failed: {gui_task}. Reason: {result.get('reason', 'Unknown error')}"
            
    except Exception as e:
        return f"Error performing GUI action: {e}"

async def main():
    print("--- Advanced Agent (Agentry Framework with Vision) ---")
    
    # Initialize Agent
    try:
        agent = Agent(
            llm="ollama", 
            model="gpt-oss:20b-cloud",
            debug=True,
            system_message="""You are an advanced autonomous agent with direct shell access and GUI control.
You can execute Windows commands using 'run_term_command' and perform visual tasks using 'perform_gui_action'.

STRATEGY FOR NATIVE APPLICATIONS:
1. If a user asks to interact with a native Windows application (e.g., Notepad, Calculator, Paint, Settings), ALWAYS try to open it first using 'run_term_command' (e.g., 'start notepad', 'start calc').
2. Once the application is open, use 'perform_gui_action' to interact with its interface.
3. Opening apps via shell provides better accessibility, focus, and faster execution than searching for icons on the desktop.

GENERAL RULES:
- Use 'run_term_command' for system-specific tasks, file management, and launching apps.
- Use 'perform_gui_action' for clicking, typing, scrolling, and reading screen content.
- Always check if a window is open or visible before performing GUI actions.
"""
        )
        agent.register_tool_from_function(run_term_command)
        agent.register_tool_from_function(perform_gui_action)
        agent.supports_tools = True

        while True:
            # Get user input if none provided in args
            if len(sys.argv) > 1:
                task = " ".join(sys.argv[1:])
                sys.argv = [sys.argv[0]] # Clear args after first run
            else:
                task = input("\n[User Request] > ")
                if task.lower() in ['exit', 'quit']:
                    break
            
            if not task:
                continue

            print(f"\nProcessing Task: {task}")
            response = await agent.chat(task)
            
            print("\n=== FINAL RESPONSE ===")
            print(response)
            
    except Exception as e:
        print(f"\n[Fatal Error] {e}")
        traceback.print_exc()

if __name__ == "__main__":
    import traceback
    asyncio.run(main())
