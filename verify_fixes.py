"""Verify all S3 agent LSP fixes."""
import sys

errors = []

# 1. Test imports
try:
    from gui_agents.s3.agents.agent_s import AgentS3, UIAgent
    print("[OK] agent_s imports")
except Exception as e:
    errors.append(f"agent_s import: {e}")
    print(f"[FAIL] agent_s import: {e}")

try:
    from gui_agents.s3.agents.code_agent import CodeAgent
    print("[OK] code_agent imports")
except Exception as e:
    errors.append(f"code_agent import: {e}")
    print(f"[FAIL] code_agent import: {e}")

try:
    from gui_agents.s3.agents.worker import Worker
    print("[OK] worker imports")
except Exception as e:
    errors.append(f"worker import: {e}")
    print(f"[FAIL] worker import: {e}")

try:
    from gui_agents.s3.core.engine import LMMEngine, LMMEngineOllama
    print("[OK] engine imports")
except Exception as e:
    errors.append(f"engine import: {e}")
    print(f"[FAIL] engine import: {e}")

try:
    from gui_agents.s3.core.mllm import LMMAgent
    print("[OK] mllm imports")
except Exception as e:
    errors.append(f"mllm import: {e}")
    print(f"[FAIL] mllm import: {e}")

try:
    from gui_agents.s3.memory.procedural_memory import PROCEDURAL_MEMORY
    print("[OK] procedural_memory imports")
except Exception as e:
    errors.append(f"procedural_memory import: {e}")
    print(f"[FAIL] procedural_memory import: {e}")

try:
    from gui_agents.s3.agents.grounding import ACI, OSWorldACI
    print("[OK] grounding imports")
except Exception as e:
    errors.append(f"grounding import: {e}")
    print(f"[FAIL] grounding import: {e}")

# 2. Test fix: UIAgent.predict returns a value
try:
    agent = UIAgent.__new__(UIAgent)
    agent.worker_engine_params = {}
    agent.grounding_agent = None
    agent.platform = "windows"
    result = agent.predict("test", {})
    assert result == ({}, []), f"Expected ({{}}, []) got {result}"
    print("[OK] UIAgent.predict returns value")
except Exception as e:
    errors.append(f"UIAgent.predict: {e}")
    print(f"[FAIL] UIAgent.predict: {e}")

# 3. Test fix: ACI base class has all attributes
try:
    aci = ACI()
    assert hasattr(aci, 'assign_screenshot'), "Missing assign_screenshot"
    assert hasattr(aci, 'set_task_instruction'), "Missing set_task_instruction"
    assert hasattr(aci, 'last_code_agent_result'), "Missing last_code_agent_result"
    assert hasattr(aci, 'wait'), "Missing wait"
    assert hasattr(aci, 'obs'), "Missing obs"
    aci.assign_screenshot({"screenshot": b"test"})
    assert aci.obs == {"screenshot": b"test"}
    aci.set_task_instruction("test task")
    assert aci.current_task_instruction == "test task"
    code = aci.wait(1.5)
    assert "time.sleep(1.5)" in code
    print("[OK] ACI base class has all needed attributes")
except Exception as e:
    errors.append(f"ACI base class: {e}")
    print(f"[FAIL] ACI base class: {e}")

# 4. Test fix: LMMEngine has generate_with_thinking
try:
    e = LMMEngineOllama(model="test")
    assert hasattr(e, 'generate_with_thinking')
    print("[OK] LMMEngine has generate_with_thinking")
except Exception as e:
    errors.append(f"generate_with_thinking: {e}")
    print(f"[FAIL] generate_with_thinking: {e}")

# 5. Test fix: CODE_SUMMARY_AGENT_PROMPT exists
try:
    assert hasattr(PROCEDURAL_MEMORY, 'CODE_SUMMARY_AGENT_PROMPT')
    assert len(PROCEDURAL_MEMORY.CODE_SUMMARY_AGENT_PROMPT) > 0
    print("[OK] CODE_SUMMARY_AGENT_PROMPT exists")
except Exception as e:
    errors.append(f"CODE_SUMMARY_AGENT_PROMPT: {e}")
    print(f"[FAIL] CODE_SUMMARY_AGENT_PROMPT: {e}")

# 6. Test fix: cli_app imports on Windows
try:
    from gui_agents.s3.cli_app import get_char, show_permission_dialog, scale_screen_dimensions
    w, h = scale_screen_dimensions(1920, 1080, 2400)
    assert w > 0 and h > 0
    print("[OK] cli_app imports on Windows")
except Exception as e:
    errors.append(f"cli_app import: {e}")
    print(f"[FAIL] cli_app import: {e}")

# Summary
print("\n" + "=" * 50)
if errors:
    print(f"FAILED: {len(errors)} error(s)")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("ALL FIXES VERIFIED SUCCESSFULLY!")
    sys.exit(0)
