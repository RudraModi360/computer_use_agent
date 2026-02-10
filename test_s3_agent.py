#!/usr/bin/env python3
"""
Simple Test Script for S3 Agent Implementation
Run this to verify all components are working correctly.
"""

import sys
import os

# Add the s3_agent_implementation to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 's3_agent_implementation'))

def test_imports():
    """Test that all modules can be imported."""
    print("\n" + "="*60)
    print("TEST 1: Module Imports")
    print("="*60)
    
    try:
        from core import LMMAgent, LMMEngineOllama
        print("[PASS] Core modules imported successfully")
        
        from memory import PROCEDURAL_MEMORY
        print("[PASS] Memory module imported successfully")
        
        from agents.grounding import OSWorldACI, agent_action
        print("[PASS] Grounding agent imported successfully")
        
        return True
    except Exception as e:
        print(f"[FAIL] Import error: {e}")
        return False


def test_llm_engines():
    """Test LLM engine initialization."""
    print("\n" + "="*60)
    print("TEST 2: LLM Engines")
    print("="*60)
    
    from core import LMMEngineOllama, LMMEngineOpenAI, LMMEngineAnthropic
    
    try:
        # Test Ollama engine
        ollama_engine = LMMEngineOllama(
            model="qwen3:0.6b",
            base_url="http://localhost:11434/v1"
        )
        print(f"[PASS] Ollama engine created (model: {ollama_engine.model})")
        
        # Test OpenAI engine
        openai_engine = LMMEngineOpenAI(
            model="gpt-4",
            api_key="test-key"
        )
        print(f"[PASS] OpenAI engine created (model: {openai_engine.model})")
        
        # Test Anthropic engine
        anthropic_engine = LMMEngineAnthropic(
            model="claude-3-sonnet",
            api_key="test-key"
        )
        print(f"[PASS] Anthropic engine created (model: {anthropic_engine.model})")
        
        return True
    except Exception as e:
        print(f"[FAIL] Engine error: {e}")
        return False


def test_mllm_agent():
    """Test MLLM agent functionality."""
    print("\n" + "="*60)
    print("TEST 3: MLLM Agent")
    print("="*60)
    
    from core import LMMAgent
    
    try:
        # Create agent
        agent = LMMAgent(
            engine_params={
                "engine_type": "ollama",
                "model": "qwen3:0.6b",
                "base_url": "http://localhost:11434/v1"
            },
            system_prompt="You are a test assistant."
        )
        print("[PASS] Agent created with system prompt")
        
        # Check initial state
        assert len(agent.messages) == 1, "Should have 1 message (system)"
        assert agent.messages[0]["role"] == "system"
        print("[PASS] Initial message state correct")
        
        # Add user message
        agent.add_message("Hello", role="user")
        assert len(agent.messages) == 2
        print("[PASS] User message added")
        
        # Add assistant message
        agent.add_message("Hi there!", role="assistant")
        assert len(agent.messages) == 3
        print("[PASS] Assistant message added")
        
        # Test reset
        agent.reset()
        assert len(agent.messages) == 1
        print("[PASS] Reset functionality works")
        
        return True
    except Exception as e:
        print(f"[FAIL] Agent error: {e}")
        return False


def test_image_handling():
    """Test image encoding."""
    print("\n" + "="*60)
    print("TEST 4: Image Handling")
    print("="*60)
    
    try:
        from PIL import Image
        from core import LMMAgent
        
        # Create test image
        img = Image.new('RGB', (100, 100), color='blue')
        temp_path = os.path.join(os.environ.get('TEMP', '/tmp'), "test_img.png")
        img.save(temp_path)
        print("[PASS] Test image created")
        
        # Create agent and encode image
        agent = LMMAgent(
            engine_params={"engine_type": "ollama", "model": "llava:7b"},
            system_prompt="Test"
        )
        
        encoded = agent.encode_image(temp_path)
        assert isinstance(encoded, str)
        assert len(encoded) > 0
        print("[PASS] Image encoded to base64")
        
        # Add message with image
        agent.add_message(
            text_content="What is this?",
            image_content=temp_path,
            role="user"
        )
        print("[PASS] Message with image added")
        
        # Cleanup
        os.remove(temp_path)
        
        return True
    except Exception as e:
        print(f"[FAIL] Image error: {e}")
        return False


def test_procedural_memory():
    """Test procedural memory system."""
    print("\n" + "="*60)
    print("TEST 5: Procedural Memory")
    print("="*60)
    
    from memory import PROCEDURAL_MEMORY
    from agents.grounding import agent_action
    
    try:
        # Check all prompts exist
        assert hasattr(PROCEDURAL_MEMORY, 'FORMATTING_FEEDBACK_PROMPT')
        print("[PASS] FORMATTING_FEEDBACK_PROMPT exists")
        
        assert hasattr(PROCEDURAL_MEMORY, 'REFLECTION_ON_TRAJECTORY')
        print("[PASS] REFLECTION_ON_TRAJECTORY exists")
        
        assert hasattr(PROCEDURAL_MEMORY, 'CODE_AGENT_PROMPT')
        print("[PASS] CODE_AGENT_PROMPT exists")
        
        assert hasattr(PROCEDURAL_MEMORY, 'PHRASE_TO_WORD_COORDS_PROMPT')
        print("[PASS] PHRASE_TO_WORD_COORDS_PROMPT exists")
        
        # Test procedural memory builder
        class TestAgent:
            @agent_action
            def click(self, x, y): pass
            
            @agent_action
            def type(self, text): pass
        
        memory = PROCEDURAL_MEMORY.construct_simple_worker_procedural_memory(TestAgent)
        assert "GUIDELINES" in memory
        assert "def click" in memory
        assert "def type" in memory
        print(f"[PASS] Procedural memory built ({len(memory)} chars)")
        
        return True
    except Exception as e:
        print(f"[FAIL] Memory error: {e}")
        return False


def test_grounding_agent():
    """Test grounding agent (ACI)."""
    print("\n" + "="*60)
    print("TEST 6: Grounding Agent (ACI)")
    print("="*60)
    
    from agents.grounding import OSWorldACI, agent_action
    
    try:
        # Initialize ACI
        aci = OSWorldACI(
            platform="windows",
            width=1920,
            height=1080
        )
        print("[PASS] ACI initialized")
        
        # Mock coordinate generator
        aci.generate_coords = lambda ref, obs: [500, 300]
        
        # Test click action
        code = aci.click("test button")
        assert "pyautogui" in code
        assert "click" in code
        assert "500" in code
        assert "300" in code
        print("[PASS] Click action generates code")
        
        # Test type action
        code = aci.type(None, "hello", enter=True)
        assert "typewrite" in code
        assert "hello" in code
        assert "enter" in code
        print("[PASS] Type action generates code")
        
        # Test hotkey action
        code = aci.hotkey(["ctrl", "s"])
        assert "hotkey" in code
        assert "ctrl" in code
        assert "s" in code
        print("[PASS] Hotkey action generates code")
        
        # Test wait action
        code = aci.wait(2.0)
        assert "sleep" in code
        assert "2.0" in code
        print("[PASS] Wait action generates code")
        
        # Test done/fail actions
        assert aci.done() == "DONE"
        assert aci.fail() == "FAIL"
        print("[PASS] Done/fail actions work")
        
        # Count agent actions
        actions = []
        for attr_name in dir(aci):
            attr = getattr(aci, attr_name)
            if callable(attr) and hasattr(attr, 'is_agent_action'):
                actions.append(attr_name)
        
        assert len(actions) == 14
        print(f"[PASS] Found {len(actions)} agent actions")
        print(f"       Actions: {', '.join(sorted(actions))}")
        
        return True
    except Exception as e:
        print(f"[FAIL] ACI error: {e}")
        return False


def test_platform_specific_actions():
    """Test platform-specific code generation."""
    print("\n" + "="*60)
    print("TEST 7: Platform-Specific Actions")
    print("="*60)
    
    from agents.grounding import OSWorldACI
    
    try:
        # Windows
        aci_win = OSWorldACI(platform="windows")
        code = aci_win.open("notepad")
        assert "win" in code.lower() or "return" in code
        print("[PASS] Windows open action works")
        
        # Mac
        aci_mac = OSWorldACI(platform="darwin")
        code = aci_mac.open("safari")
        assert "command" in code or "space" in code
        print("[PASS] Mac open action works")
        
        # Linux
        aci_linux = OSWorldACI(platform="linux")
        code = aci_linux.open("firefox")
        assert "win" in code.lower() or "return" in code
        print("[PASS] Linux open action works")
        
        return True
    except Exception as e:
        print(f"[FAIL] Platform error: {e}")
        return False


def test_observation_management():
    """Test observation and task management."""
    print("\n" + "="*60)
    print("TEST 8: Observation Management")
    print("="*60)
    
    from agents.grounding import OSWorldACI
    
    try:
        aci = OSWorldACI()
        
        # Test screenshot assignment
        mock_obs = {"screenshot": b"fake_data", "width": 1920, "height": 1080}
        aci.assign_screenshot(mock_obs)
        assert aci.obs == mock_obs
        print("[PASS] Screenshot observation assigned")
        
        # Test task instruction
        aci.set_task_instruction("Test task")
        assert aci.current_task_instruction == "Test task"
        print("[PASS] Task instruction set")
        
        # Test notes
        aci.save_to_knowledge(["Note 1", "Note 2"])
        assert len(aci.notes) == 2
        assert "Note 1" in aci.notes
        print("[PASS] Knowledge notes saved")
        
        return True
    except Exception as e:
        print(f"[FAIL] Observation error: {e}")
        return False


def run_all_tests():
    """Run all tests and print summary."""
    print("\n" + "="*60)
    print("S3 AGENT - SIMPLE TEST SUITE")
    print("="*60)
    print("\nTesting all core components...\n")
    
    tests = [
        ("Module Imports", test_imports),
        ("LLM Engines", test_llm_engines),
        ("MLLM Agent", test_mllm_agent),
        ("Image Handling", test_image_handling),
        ("Procedural Memory", test_procedural_memory),
        ("Grounding Agent", test_grounding_agent),
        ("Platform-Specific", test_platform_specific_actions),
        ("Observation Management", test_observation_management),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n[ERROR] Test '{name}' crashed: {e}")
            results.append((name, False))
    
    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "PASS" if result else "FAIL"
        symbol = "[OK]" if result else "[XX]"
        print(f"{symbol} {name}")
    
    print("\n" + "="*60)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n[OK] ALL TESTS PASSED!")
        print("\nYour S3 Agent implementation is working correctly.")
        print("You can now proceed to build the remaining components:")
        print("  - Code Agent")
        print("  - Worker Agent")
        print("  - AgentS3 Main")
        print("  - CLI Application")
        return 0
    else:
        print(f"\n[WARNING] {total - passed} test(s) failed")
        print("Please check the errors above.")
        return 1


if __name__ == "__main__":
    try:
        exit_code = run_all_tests()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
