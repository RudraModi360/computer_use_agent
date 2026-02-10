"""
VLM Prompt Templates for Computer Use Agent
"""

SYSTEM_PROMPT = """You are a computer use agent. You can interact with the computer by clicking on UI elements, typing text, and scrolling.

You will receive:
1. An original screenshot of the current screen
2. An annotated screenshot with numbered bounding boxes for each detected UI element
3. A list of detected elements with their IDs, types, positions, and any visible text

Your job is to analyze the screen and decide what actions to take to complete the given task.

IMPORTANT RULES:
- Always refer to elements by their ID number (e.g., "click 5" means click element [5])
- Think step by step about what you see and what action to take
- Only output ONE action at a time
- If you can't find a required element, say "WAIT" and describe what you're looking for
- When the task is complete, output "DONE"

OUTPUT FORMAT:
First, briefly describe what you see and your reasoning.
Then output your action on a new line starting with "ACTION:"

Available actions:
- ACTION: click <element_id>
- ACTION: type "<text>"
- ACTION: scroll <up|down|left|right>
- ACTION: press <key>  (e.g., press enter, press tab)
- ACTION: wait
- ACTION: done
"""

TASK_PROMPT_TEMPLATE = """
DETECTED ELEMENTS:
{element_list}

CURRENT TASK: {task}

{history_section}

What action should be taken next?
"""

HISTORY_SECTION_TEMPLATE = """
PREVIOUS ACTIONS IN THIS TASK:
{action_history}
"""

FEEDBACK_PROMPT_TEMPLATE = """
FEEDBACK FROM LAST ACTION:
The last action was: {last_action}
Result: {feedback}

Detected changes on screen:
{screen_changes}

Based on this feedback, what should be the next action?
"""


def build_task_prompt(element_list: str, task: str, 
                      action_history: list = None) -> str:
    """Build the task prompt with element list and optional history."""
    history_section = ""
    if action_history:
        history_text = "\n".join([f"  {i+1}. {action}" for i, action in enumerate(action_history)])
        history_section = HISTORY_SECTION_TEMPLATE.format(action_history=history_text)
    
    return TASK_PROMPT_TEMPLATE.format(
        element_list=element_list,
        task=task,
        history_section=history_section
    )


def build_feedback_prompt(last_action: str, feedback: str, 
                          screen_changes: str = "No significant changes detected") -> str:
    """Build a feedback prompt for the VLM."""
    return FEEDBACK_PROMPT_TEMPLATE.format(
        last_action=last_action,
        feedback=feedback,
        screen_changes=screen_changes
    )


def parse_action(response: str) -> dict:
    """
    Parse VLM response to extract the action.
    
    Returns:
        dict with 'type' and 'value' keys
    """
    lines = response.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if line.upper().startswith('ACTION:'):
            action_part = line[7:].strip()
            
            # Parse different action types
            action_lower = action_part.lower()
            
            if action_lower.startswith('click'):
                try:
                    elem_id = int(action_part.split()[1])
                    return {'type': 'click', 'element_id': elem_id}
                except (IndexError, ValueError):
                    return {'type': 'error', 'message': f'Invalid click action: {action_part}'}
            
            elif action_lower.startswith('type'):
                # Extract text between quotes
                import re
                match = re.search(r'"([^"]*)"', action_part)
                if match:
                    return {'type': 'type', 'text': match.group(1)}
                else:
                    # Try without quotes
                    text = action_part[4:].strip().strip('"\'')
                    return {'type': 'type', 'text': text}
            
            elif action_lower.startswith('scroll'):
                direction = action_part.split()[1] if len(action_part.split()) > 1 else 'down'
                return {'type': 'scroll', 'direction': direction}
            
            elif action_lower.startswith('press'):
                key = action_part.split()[1] if len(action_part.split()) > 1 else 'enter'
                return {'type': 'press', 'key': key}
            
            elif action_lower == 'wait':
                return {'type': 'wait'}
            
            elif action_lower == 'done':
                return {'type': 'done'}
            
            else:
                return {'type': 'unknown', 'raw': action_part}
    
    # No action found
    return {'type': 'none', 'raw_response': response[:200]}


if __name__ == "__main__":
    # Test prompt building
    elements = """[1] input_field at (300, 220) - "Search..."
[2] button at (460, 220) - "Go"
[3] navbar at (400, 30)"""
    
    prompt = build_task_prompt(elements, "Search for 'weather'")
    print("Generated prompt:")
    print(prompt)
    
    # Test action parsing
    test_responses = [
        "I see a search box. \nACTION: click 1",
        "Typing the query.\nACTION: type \"weather\"",
        "ACTION: scroll down",
        "Task complete! ACTION: done",
    ]
    
    print("\nParsing test responses:")
    for resp in test_responses:
        parsed = parse_action(resp)
        print(f"  '{resp[:30]}...' -> {parsed}")
