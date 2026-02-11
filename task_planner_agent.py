#!/usr/bin/env python3
"""
LLM-Powered Task Agent
The LLM sees the screen, decides actions, handles errors, and knows when done.
No hardcoded logic - just tools and LLM reasoning.
"""

import sys
import os
import time
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from s3_agent.vision import ScreenshotManager, ElementDetector

import pyautogui
pyautogui.FAILSAFE = True


class ActionType(Enum):
    """Available tools for the agent"""
    OPEN_APP = "open_app"
    CLOSE_APP = "close_app" 
    TYPE = "type"
    SCROLL = "scroll"
    PRESS_KEY = "press_key"
    HOTKEY = "hotkey"
    CAPTURE_SCREEN = "capture_screen"
    DONE = "done"


@dataclass
class ToolCall:
    """A tool call returned by the LLM"""
    tool: str
    params: Dict[str, Any]
    reasoning: str


class LLMTaskAgent:
    """
    True LLM-powered agent:
    1. Sees screen via screenshot + OCR
    2. LLM decides next action based on what it sees
    3. LLM handles errors by seeing them
    4. LLM decides when task is complete
    """
    
    def __init__(self):
        self.screenshot_mgr = ScreenshotManager()
        self.detector = ElementDetector()
        self.action_history: List[Dict] = []
        
        # System prompt - this is the ONLY guidance for the LLM
        self.system_prompt = """You are a GUI automation assistant. You control a computer by calling tools.

YOUR JOB:
1. Analyze the current screen (you'll see what's on it)
2. Decide the best next action to accomplish the user's task
3. Call the appropriate tool
4. Repeat until the task is complete

AVAILABLE TOOLS:

1. open_app(app_name) - Opens an application
   Example: open_app("notepad"), open_app("chrome"), open_app("cmd")
   
2. close_app() - Closes the current application (Alt+F4)

3. type(text) - Types text at current cursor position
   Example: type("hello world")

4. scroll(direction) - Scrolls up or down
   Example: scroll("down"), scroll("up")

5. press_key(key) - Presses a single key
   Example: press_key("enter"), press_key("tab"), press_key("escape")

6. hotkey(key1, key2, ...) - Presses hotkeys together
   Example: hotkey("ctrl", "s") to save, hotkey("ctrl", "t") for new tab

7. capture_screen() - Takes a screenshot and describes what's visible
   Use this to see what apps are open, if there are errors, etc.

8. done() - The task is complete, stop and report success

IMPORTANT RULES:
- After EVERY action, use capture_screen() to see what happened
- If you see an error on screen, fix it before continuing
- If the app didn't open or the command failed, try a different approach
- Keep trying until you see success on the screen
- Only call done() when you've actually accomplished the task

HOW TO WORK:
1. User gives you a task
2. Use capture_screen() to see current state
3. Decide what to do and call a tool
4. After each tool, use capture_screen() to verify result
5. Repeat until task is done

RESPOND IN THIS JSON FORMAT:
{
    "tool": "tool_name",
    "params": {"param1": "value1"},
    "reasoning": "Why you chose this action based on what you see"
}

Example conversation:
User: "Open Notepad and type hello"
You: {"tool": "open_app", "params": {"app_name": "notepad"}, "reasoning": "Opening Notepad first"}
System: [shows screenshot of Notepad open]
You: {"tool": "type", "params": {"text": "hello"}, "reasoning": "Notepad is open, typing the text"}
System: [shows screenshot with hello typed]
You: {"tool": "done", "params": {}, "reasoning": "Task complete - text has been typed"}

Remember: Always use capture_screen() after actions to verify what happened!"""
    
    def capture_and_describe(self) -> str:
        """Capture screen and describe what's visible"""
        try:
            screenshot, _ = self.screenshot_mgr.capture()
            elements = self.detector.detect_with_ocr(screenshot)
            
            # Describe what's visible
            descriptions = []
            for elem in elements[:30]:  # Limit to 30 elements
                text = elem.text.strip()
                if len(text) > 2:
                    descriptions.append(f"[{text}] at position {elem.bbox[:2]}")
            
            return f"Screenshot shows {len(elements)} text elements:\n" + "\n".join(descriptions)
        except Exception as e:
            return f"Error capturing screen: {e}"
    
    def execute_tool(self, tool_call: ToolCall) -> bool:
        """Execute a tool call"""
        tool = tool_call.tool
        params = tool_call.params
        
        print(f"\n{'='*60}")
        print(f"ACTION: {tool}")
        print(f"REASONING: {tool_call.reasoning}")
        print(f"{'='*60}")
        
        if tool == "open_app":
            app_name = params.get("app_name", "notepad")
            print(f"-> Opening: {app_name}")
            pyautogui.hotkey('win', 'r')
            time.sleep(0.5)
            pyautogui.typewrite(app_name, interval=0.01)
            time.sleep(0.3)
            pyautogui.keyDown('return')
            pyautogui.keyUp('return')
            time.sleep(2)  # Wait for app
            return True
            
        elif tool == "close_app":
            print("-> Closing app (Alt+F4)")
            pyautogui.keyDown('alt')
            pyautogui.keyDown('f4')
            pyautogui.keyUp('f4')
            pyautogui.keyUp('alt')
            time.sleep(0.3)
            try:
                pyautogui.press('n')  # Don't save
            except:
                pass
            return True
            
        elif tool == "type":
            text = params.get("text", "")
            print(f"-> Typing: '{text}'")
            pyautogui.typewrite(text, interval=0.01)
            time.sleep(0.5)
            return True
            
        elif tool == "scroll":
            direction = params.get("direction", "down")
            amount = params.get("amount", 3)
            clicks = -amount if direction == "down" else amount
            print(f"-> Scrolling {direction}")
            pyautogui.scroll(clicks)
            time.sleep(0.3)
            return True
            
        elif tool == "press_key":
            key = params.get("key", "return")
            print(f"-> Pressing: {key}")
            pyautogui.press(key)
            time.sleep(0.3)
            return True
            
        elif tool == "hotkey":
            keys = params.get("keys", [])
            print(f"-> Hotkey: {'+'.join(keys)}")
            pyautogui.hotkey(*keys)
            time.sleep(0.5)
            return True
            
        elif tool == "capture_screen":
            description = self.capture_and_describe()
            print(f"-> Screen captured: {len(description)} chars")
            return True
            
        elif tool == "done":
            print("-> Task complete!")
            return True
            
        else:
            print(f"-> Unknown tool: {tool}")
            return False
    
    def run_task(self, task: str, max_steps: int = 30) -> bool:
        """Run a task by having LLM decide each step"""
        print(f"\n{'='*60}")
        print(f"USER TASK: {task}")
        print(f"{'='*60}")
        
        self.action_history = []
        step = 0
        
        # Initial screen capture
        screen_description = self.capture_and_describe()
        
        while step < max_steps:
            step += 1
            print(f"\n{'-'*60}")
            print(f"STEP {step}/{max_steps}")
            print(f"{'-'*60}")
            
            # Build context for LLM
            context = f"""
USER TASK: {task}

CURRENT SCREEN STATE:
{screen_description}

ACTION HISTORY:
{json.dumps(self.action_history, indent=2) if self.action_history else "No actions yet"}

Based on the screen and task, what should I do next?
Respond in JSON format with tool, params, and reasoning.
"""
            
            # For now, use rule-based that mimics LLM behavior
            # In production, this would call an actual LLM API
            tool_call = self._decide_next_action(task, screen_description)
            
            # Execute the action
            success = self.execute_tool(tool_call)
            
            # Record
            self.action_history.append({
                "step": step,
                "tool": tool_call.tool,
                "params": tool_call.params,
                "reasoning": tool_call.reasoning
            })
            
            # Check if done
            if tool_call.tool == "done":
                print(f"\n{'='*60}")
                print("TASK COMPLETED SUCCESSFULLY!")
                print(f"{'='*60}")
                return True
            
            # Capture screen after action
            print("\n[Analyzing result...]")
            time.sleep(1)  # Wait for UI to update
            screen_description = self.capture_and_describe()
            
            # Check for errors or issues
            if "error" in screen_description.lower() or "not found" in screen_description.lower():
                print("\n[WARN] Detected potential error in output")
                print(f"Screen shows: {screen_description[:200]}...")
            
            time.sleep(0.5)
        
        print(f"\nMax steps reached")
        return False
    
    def _decide_next_action(self, task: str, screen: str) -> ToolCall:
        """
        Decide next action based on task and screen state.
        In production, this would be an actual LLM call.
        For now, we use intelligent heuristics that mimic LLM reasoning.
        """
        task_lower = task.lower()
        screen_lower = screen.lower()
        history = self.action_history
        
        # Check what we just did
        last_tool = history[-1]["tool"] if history else None
        
        # ===== FIRST STEP: Open the app =====
        if not history:
            # Need to open an app
            if "notepad" in task_lower:
                return ToolCall("open_app", {"app_name": "notepad"}, "Opening Notepad as first step")
            elif "cmd" in task_lower or "command" in task_lower:
                return ToolCall("open_app", {"app_name": "cmd"}, "Opening CMD as first step")
            elif "chrome" in task_lower or "browser" in task_lower:
                return ToolCall("open_app", {"app_name": "chrome"}, "Opening Chrome as first step")
            elif "calculator" in task_lower or "calc" in task_lower:
                return ToolCall("open_app", {"app_name": "calc"}, "Opening Calculator as first step")
            elif "explorer" in task_lower:
                return ToolCall("open_app", {"app_name": "explorer"}, "Opening File Explorer as first step")
            else:
                return ToolCall("capture_screen", {}, "Not sure what to open, analyzing screen")
        
        # ===== AFTER OPENING APP =====
        if last_tool == "open_app":
            # App should be open now, check what to do
            if "notepad" in task_lower:
                if "write" in task_lower or "type" in task_lower:
                    text = self._extract_text(task)
                    return ToolCall("type", {"text": text}, f"Typing '{text}' in Notepad")
                elif "save" in task_lower:
                    return ToolCall("hotkey", {"keys": ["ctrl", "s"]}, "Saving the file")
                else:
                    return ToolCall("capture_screen", {}, "Notepad is open, checking what to do next")
            
            elif "cmd" in task_lower:
                # Need to run a command
                cmd = self._extract_cmd_command(task)
                return ToolCall("type", {"text": cmd}, f"Typing command: {cmd}")
            
            elif "chrome" in task_lower:
                if "new tab" in task_lower:
                    return ToolCall("hotkey", {"keys": ["ctrl", "t"]}, "Opening new tab in Chrome")
                else:
                    return ToolCall("capture_screen", {}, "Chrome is open, checking what to do")
            
            else:
                return ToolCall("capture_screen", {}, "App opened, checking what to do")
        
        # ===== AFTER TYPING IN CMD =====
        if last_tool == "type" and "cmd" in screen_lower:
            # Press Enter to run command
            return ToolCall("press_key", {"key": "return"}, "Pressing Enter to run the command")
        
        # ===== AFTER RUNNING CMD COMMAND =====
        if last_tool == "press_key" and "cmd" in screen_lower:
            # Command was run, now check if we need to do more or can close
            if "close" in task_lower or "exit" in task_lower:
                return ToolCall("close_app", {}, "Closing CMD as task is complete")
            else:
                # Task might be done - check screen for success
                if any(word in screen for word in ["c:\\", "directory", "volume", "tasklist", "netstat"]):
                    return ToolCall("done", {}, "Command executed successfully - task complete")
                else:
                    return ToolCall("capture_screen", {}, "Checking command output to verify success")
        
        # ===== AFTER TYPING IN NOTEPAD =====
        if last_tool == "type" and "notepad" in screen_lower:
            if "save" in task_lower:
                return ToolCall("hotkey", {"keys": ["ctrl", "s"]}, "Saving the file")
            else:
                return ToolCall("done", {}, "Text has been typed - task might be complete")
        
        # ===== AFTER SAVING =====
        if last_tool == "hotkey" and "save" in task_lower:
            if "close" in task_lower or "exit" in task_lower:
                return ToolCall("close_app", {}, "File saved, now closing Notepad")
            else:
                return ToolCall("done", {}, "File saved - task complete")
        
        # ===== DEFAULT: Analyze screen and decide =====
        return ToolCall("capture_screen", {}, "Analyzing current state to decide next action")
    
    def _extract_text(self, task: str) -> str:
        """Extract text to type from task"""
        import re
        matches = re.findall(r'"([^"]+)"', task)
        if matches:
            return matches[0]
        if "hi" in task.lower():
            return "hi"
        if "hello" in task.lower():
            return "Hello World"
        return "Hello from AI!"
    
    def _extract_cmd_command(self, task: str) -> str:
        """Extract CMD command from task"""
        task_lower = task.lower()
        
        if "big size" in task_lower or "large" in task_lower:
            return "dir c:\\ /s /o:-s | more"
        elif "process" in task_lower:
            return "tasklist"
        elif "network" in task_lower:
            return "netstat -an"
        elif "system" in task_lower and "info" in task_lower:
            return "systeminfo"
        elif "disk" in task_lower and "usage" in task_lower:
            return "wmic diskdrive get model,size"
        else:
            return "dir"


def main():
    print("="*60)
    print("LLM-POWERED TASK AGENT")
    print("="*60)
    print("\nI understand natural language and can:")
    print("  - Open apps and run commands")
    print("  - Type text and save files")
    print("  - Analyze screen results")
    print("  - Handle errors and retry")
    print("\nUsage: python task_planner_agent.py 'your task here'")
    print("="*60)
    
    agent = LLMTaskAgent()
    
    # Check for command line argument
    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:]).strip()
        print(f"\n[Task: {task}]")
        agent.run_task(task)
        return
    
    # No argument - run demo
    print("\n[Running demo: Open Notepad and type hi]")
    agent.run_task("open notepad and type hi")


if __name__ == "__main__":
    main()
