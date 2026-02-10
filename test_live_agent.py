"""Quick live test of Smart Agent with Ollama."""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from smart_agent import SmartAgent

def main():
    print("=" * 60)
    print("SMART AGENT LIVE TEST")
    print("=" * 60)
    
    # Initialize with the fast qwen3:0.6b model
    agent = SmartAgent(
        vlm_backend="ollama",
        vlm_model="qwen3:0.6b",
        vlm_host="http://localhost:11434",
        output_dir="agent_output",
        max_retries=1
    )
    
    # Simple task: open Notepad
    task = "Open Notepad"
    results = agent.run(task, max_steps=3)
    
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(agent.get_summary())
    
    # Check if any step succeeded
    successes = sum(1 for r in results if r.success)
    print(f"\nSuccessful steps: {successes}/{len(results)}")


if __name__ == "__main__":
    main()
