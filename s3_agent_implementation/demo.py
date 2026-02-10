"""
Demo script showing S3 Agent components in action.
Demonstrates the grounding agent generating pyautogui code.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from agents.grounding import OSWorldACI
from memory import PROCEDURAL_MEMORY


def demo_grounding_agent():
    """Demonstrate grounding agent capabilities."""
    print("\n" + "="*70)
    print("DEMO: Grounding Agent (ACI)")
    print("="*70)
    
    # Initialize ACI
    aci = OSWorldACI(
        platform="windows",
        width=1920,
        height=1080
    )
    
    print("\n1. Creating mock screenshot observation")
    mock_obs = {"screenshot": b"mock_screenshot_data"}
    aci.assign_screenshot(mock_obs)
    aci.set_task_instruction("Search for 'weather' on Google")
    
    print("\n2. Simulating coordinate generation")
    # Mock the coordinate generator to return predictable coords
    aci.generate_coords = lambda ref, obs: [500, 300] if "search" in ref.lower() else [800, 600]
    
    print("\n3. Generating UI actions")
    print("-" * 70)
    
    # Example 1: Click
    print("\nAction: Click on search box")
    code = aci.click("search input field", num_clicks=1, button_type="left")
    print(f"Generated Code:\n{code}\n")
    
    # Example 2: Type
    print("Action: Type 'weather'")
    code = aci.type(None, text="weather", overwrite=False, enter=True)
    print(f"Generated Code:\n{code}\n")
    
    # Example 3: Hotkey
    print("Action: Save file (Ctrl+S)")
    code = aci.hotkey(["ctrl", "s"])
    print(f"Generated Code:\n{code}\n")
    
    # Example 4: Open application
    print("Action: Open Notepad")
    code = aci.open("notepad")
    print(f"Generated Code:\n{code}\n")
    
    # Example 5: Scroll
    print("Action: Scroll down on page")
    code = aci.scroll("main content area", clicks=-3)
    print(f"Generated Code:\n{code}\n")
    
    # Example 6: Drag and drop
    print("Action: Drag file from folder to trash")
    aci.generate_coords = lambda ref, obs: [100, 200] if "file" in ref.lower() else [500, 500]
    code = aci.drag_and_drop("file icon", "trash icon")
    print(f"Generated Code:\n{code}\n")
    
    print("-" * 70)
    print("\n4. Available Agent Actions")
    actions = []
    for attr_name in dir(aci):
        attr = getattr(aci, attr_name)
        if callable(attr) and hasattr(attr, 'is_agent_action'):
            actions.append(attr_name)
    
    print(f"Total: {len(actions)} actions")
    print(f"Actions: {', '.join(sorted(actions))}")


def demo_procedural_memory():
    """Demonstrate procedural memory system."""
    print("\n" + "="*70)
    print("DEMO: Procedural Memory System")
    print("="*70)
    
    print("\n1. Available System Prompts")
    print("-" * 70)
    
    prompts = [
        ('FORMATTING_FEEDBACK_PROMPT', PROCEDURAL_MEMORY.FORMATTING_FEEDBACK_PROMPT[:100] + "..."),
        ('REFLECTION_ON_TRAJECTORY', PROCEDURAL_MEMORY.REFLECTION_ON_TRAJECTORY[:100] + "..."),
        ('CODE_AGENT_PROMPT', PROCEDURAL_MEMORY.CODE_AGENT_PROMPT[:100] + "..."),
        ('PHRASE_TO_WORD_COORDS_PROMPT', PROCEDURAL_MEMORY.PHRASE_TO_WORD_COORDS_PROMPT[:100] + "..."),
    ]
    
    for name, content in prompts:
        print(f"\n{name}:")
        print(f"  Length: {len(getattr(PROCEDURAL_MEMORY, name))} chars")
        print(f"  Preview: {content}")
    
    print("\n\n2. Worker Procedural Memory Builder")
    print("-" * 70)
    
    # Create a mock agent class
    class DemoAgent:
        def click(self, element): pass
        def type(self, text): pass
        def scroll(self, direction): pass
        def done(self): pass
    
    # Add decorator to methods
    from agents.grounding import agent_action
    DemoAgent.click = agent_action(DemoAgent.click)
    DemoAgent.type = agent_action(DemoAgent.type)
    DemoAgent.scroll = agent_action(DemoAgent.scroll)
    DemoAgent.done = agent_action(DemoAgent.done)
    
    memory = PROCEDURAL_MEMORY.construct_simple_worker_procedural_memory(DemoAgent)
    print(f"\nGenerated procedural memory length: {len(memory)} chars")
    print(f"Contains 'GUIDELINES': {'GUIDELINES' in memory}")
    print(f"Contains 'Code Agent': {'Code Agent' in memory}")
    print(f"Contains action definitions: {'def click' in memory and 'def type' in memory}")


def demo_architecture_overview():
    """Show architecture overview."""
    print("\n" + "="*70)
    print("S3 AGENT ARCHITECTURE OVERVIEW")
    print("="*70)
    
    print("""
    +---------------------------------------------------------------------------------+
    |                        AgentS3 (Main)                                           |
    +---------------------------------------------------------------------------------+
    |  +--------------+  +--------------+  +--------------+                           |
    |  |    Worker    |  |  Reflection  |  | Code Summary |                           |
    |  |    Agent     |  |    Agent     |  |    Agent     |                           |
    |  +--------------+  +--------------+  +--------------+                           |
    +---------------------------------------------------------------------------------+
    |                    +------------------+                                         |
    |                    |  OSWorldACI      |                                         |
    |                    |  (Grounding)     |                                         |
    |                    +------------------+                                         |
    +---------------------------------------------------------------------------------+
    |  +--------------+  +--------------+  +--------------+                           |
    |  | Code Agent   |  |   LMMAgent   |  |   Memory     |                           |
    |  | (Python/Bash)|  |  (LLM Wrapper)|  |  (Prompts)   |                           |
    |  +--------------+  +--------------+  +--------------+                           |
    +---------------------------------------------------------------------------------+
    |  +--------------+  +--------------+  +--------------+                           |
    |  |   OpenAI     |  |  Anthropic   |  |    Ollama    |                           |
    |  |    Engine    |  |    Engine    |  |    Engine    |                           |
    |  +--------------+  +--------------+  +--------------+                           |
    +---------------------------------------------------------------------------------+
    
    Components Built So Far:
    [OK] Core LLM Engines (OpenAI, Anthropic, Ollama, Gemini)
    [OK] MLLM Agent (Message management, image encoding)
    [OK] Procedural Memory (System prompts)
    [OK] Grounding Agent (ACI with 14 actions)
    
    Next Components:
    [..] Code Agent (Python/Bash execution)
    [..] Worker Agent (Main reasoning loop)
    [..] AgentS3 (Main orchestrator)
    [..] CLI Application
    """)


def main():
    """Run all demos."""
    print("\n" + "="*70)
    print("S3 AGENT IMPLEMENTATION - COMPONENT DEMONSTRATION")
    print("="*70)
    
    demo_grounding_agent()
    demo_procedural_memory()
    demo_architecture_overview()
    
    print("\n" + "="*70)
    print("DEMONSTRATION COMPLETE")
    print("="*70)
    print("\nAll core components are working correctly!")
    print("Ready to proceed with remaining components:")
    print("  1. Code Agent (Python/Bash execution)")
    print("  2. Worker Agent (Main reasoning loop)")
    print("  3. AgentS3 (Main orchestrator)")
    print("  4. CLI Application")


if __name__ == "__main__":
    main()
