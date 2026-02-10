"""Tool-calling prompts for Smart Agent."""

TOOL_CALLING_SYSTEM = """You are a computer automation agent. You complete tasks by using tools.

AVAILABLE TOOLS:

1. run_command(command: str)
   Execute a shell command. Use for: opening apps, running scripts, file operations.
   Examples:
   - run_command("notepad.exe") - opens Notepad
   - run_command("start https://www.google.com/search?q=query") - Search directly in default browser (Windows)
   - run_command("start chrome https://google.com") - opens Chrome with URL
   - run_command("dir") - list files

2. keyboard(action: str, text?: str, key?: str, keys?: list)
   Control keyboard. Actions: "type", "press", "hotkey"
   Examples:
   - keyboard("type", text="Hello World") - types text
   - keyboard("press", key="enter") - presses Enter
   - keyboard("hotkey", keys=["ctrl", "s"]) - Ctrl+S

3. computer_use(action: str, element_id?: int, direction?: str, query?: str)
   UI interaction. Actions: "detect", "click", "scroll", "find", "refine"
   Examples:
   - computer_use("detect") - capture screen and detect UI elements
   - computer_use("click", element_id=5) - click element [5]
   - computer_use("find", query="Save") - find elements with "Save" text
   - computer_use("scroll", direction="down") - scroll down

4. read_screen()
   Capture current screen state.

5. wait(seconds: float)
   Wait for a specified duration. Use when waiting for pages to load.
   Example: wait(2.0)

RULES:
- Think step by step about the most efficient approach
- VERIFY: After every action, look at the "LAST SCREEN" info to see if your action worked.
- SEARCH Tasks: If asked to "find" or "search" for information not on screen, ALWAYS start by opening a browser with `run_command("start chrome https://google.com/search?q=...")`
- APP Tasks: If asked to open an app, use `run_command` first.
- If you opened an app, wait to see it in the element list before typing.
- If your previous action failed to change the screen as expected, RETRY or try a different approach.
- Prefer run_command for opening apps (faster than UI navigation)
- Use keyboard after an app is focused
- Use computer_use for UI navigation when needed
- Always respond with EXACTLY ONE tool call
- IMPORTANT: When you have successfully executed the final action of the task AND verified it on screen, you MUST use the "done" tool.

OUTPUT FORMAT:
First, briefly explain your reasoning (1-2 sentences).
Then output the tool call on a new line:

TOOL: tool_name
PARAMS: {"param": "value"}

When task is complete, you MUST respond with:
TOOL: done
PARAMS: {}
"""

TOOL_CALL_TEMPLATE = """
{context}

What is the next action to complete the task?
"""


def build_tool_prompt(context: str) -> str:
    """Build the tool calling prompt."""
    return TOOL_CALL_TEMPLATE.format(context=context)


def parse_tool_call(response: str) -> dict:
    """
    Parse VLM response to extract tool call.
    
    Returns:
        dict with 'tool' and 'params' keys
    """
    import json
    import re
    
    lines = response.strip().split('\n')
    
    tool_name = None
    params = {}
    
    for i, line in enumerate(lines):
        line = line.strip()
        
        # Find TOOL: line
        if line.upper().startswith('TOOL:'):
            tool_name = line[5:].strip().lower()
            
            # Look for PARAMS: on next line or same line
            for j in range(i, min(i + 3, len(lines))):
                param_line = lines[j].strip()
                if param_line.upper().startswith('PARAMS:'):
                    params_str = param_line[7:].strip()
                    
                    # Try to parse JSON
                    try:
                        # Handle both {} format and key=value format
                        if params_str.startswith('{'):
                            params = json.loads(params_str)
                        else:
                            # Simple key=value parsing
                            params = {}
                    except json.JSONDecodeError:
                        # Try to extract from malformed JSON
                        try:
                            # Find JSON-like content
                            match = re.search(r'\{[^}]+\}', param_line)
                            if match:
                                params = json.loads(match.group())
                        except:
                            params = {}
                    break
            break
    
    # Normalize tool names
    original_tool = tool_name
    if tool_name == 'click':
        tool_name = 'computer_use'
        # If params has 'action', it's likely the ID if it's an int
        if 'action' in params and str(params['action']).isdigit():
             params['element_id'] = int(params['action'])
             params['action'] = 'click'
        elif not params and 'raw' in locals():
             pass # Will be handled by regex below
             
    elif tool_name in ['type', 'press', 'hotkey']:
        tool_name = 'keyboard'
        if 'action' in params and original_tool == 'type':
             params['text'] = params.pop('action')
             params['action'] = 'type'
             
    elif tool_name in ['open', 'start', 'exec']:
        tool_name = 'run_command'
    elif tool_name in ['find']:
        tool_name = 'computer_use'
        params['action'] = 'find'

    # Handle common fuzzy variations if no explicit tool found
    if not tool_name:
        # Try to find action-like patterns
        response_lower = response.lower()
        if 'run_command' in response_lower or 'notepad' in response_lower:
            tool_name = 'run_command'
        elif 'keyboard' in response_lower: 
            tool_name = 'keyboard'
        elif 'computer_use' in response_lower:
            tool_name = 'computer_use'
        elif 'read_screen' in response_lower:
            tool_name = 'read_screen'
        elif 'wait' in response_lower:
            tool_name = 'wait'
        elif 'click' in response_lower:
            tool_name = 'computer_use'
        elif 'type' in response_lower:
            tool_name = 'keyboard'
        elif 'done' in response_lower or 'complete' in response_lower:
            tool_name = 'done'
            
        # Try to extract command
        if tool_name == 'run_command':
            match = re.search(r'(?:run_command\s*\(?\s*["\'])([^"\']+)', response, re.I)
            if match: params = {'command': match.group(1)}
            elif 'notepad' in response_lower: params = {'command': 'notepad.exe'}
        elif tool_name == 'keyboard':
            match = re.search(r'(?:text\s*[=:]\s*["\']|type\s*["\'])([^"\']+)', response, re.I)
            if match: params = {'action': 'type', 'text': match.group(1)}
        elif tool_name == 'computer_use':
            match = re.search(r'(?:element[_\s]*id\s*[=:]\s*|click\s*)(\d+)', response, re.I)
            if match: params = {'action': 'click', 'element_id': int(match.group(1))}
            else: params = {'action': 'detect'}
        elif tool_name == 'wait':
            match = re.search(r'(?:wait\s*\(?\s*)(\d+\.?\d*)', response, re.I)
            if match: params = {'seconds': float(match.group(1))}
    
    # Final backup: check if params is empty and tool is run_command
    if tool_name == 'run_command' and not params:
        # Try to extract anything that looks like a command
        match = re.search(r'["\']([^"\']+\.exe[^"\']*)["\']', response)
        if match:
            params = {'command': match.group(1)}
        elif 'notepad' in response_lower:
            params = {'command': 'notepad.exe'}
    
    # Normalize parameters
    if params:
        # Some models use 'param' instead of 'action'
        if 'param' in params and 'action' not in params:
            params['action'] = params.pop('param')
            
        # Specific fix for run_command
        if tool_name == 'run_command':
            if 'action' in params and 'command' not in params:
                params['command'] = params.pop('action')
        
        # Specific fix for computer_use (ensure action is present)
        if tool_name == 'computer_use':
            if 'action' not in params:
                if 'element_id' in params:
                    params['action'] = 'click'
                elif 'query' in params:
                    params['action'] = 'find'
                elif 'direction' in params:
                    params['action'] = 'scroll'
                else:
                    params['action'] = 'detect'
    
    return {
        'tool': tool_name,
        'params': params,
        'raw': response
    }


# Quick test
if __name__ == "__main__":
    test_responses = [
        "I'll open Notepad.\nTOOL: run_command\nPARAMS: {\"command\": \"notepad.exe\"}",
        "Now I'll type the text.\nTOOL: keyboard\nPARAMS: {\"action\": \"type\", \"text\": \"Hello World\"}",
        "Task complete!\nTOOL: done\nPARAMS: {}",
        "Let me click on the search box.\nTOOL: computer_use\nPARAMS: {\"action\": \"click\", \"element_id\": 5}",
    ]
    
    print("Testing tool call parsing:")
    for resp in test_responses:
        parsed = parse_tool_call(resp)
        print(f"  {parsed['tool']}: {parsed['params']}")
