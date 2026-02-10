"""Test the Smart Agent with a simple task."""
from smart_agent import SmartAgent

# Use a small fast model for tool routing
agent = SmartAgent(
    vlm_model="gpt-oss:20b-cloud",  # Fast model for tool decisions
    output_dir="agent_output"
)

# Run a simple task
results = agent.run("find the recent udpates of Liquid AI model itself, open the official website and gather the  details from it ", max_steps=10)

# Print summary
print("\n" + "="*50)
print("📊 SUMMARY")
print("="*50)
print(agent.get_summary())
print("\n" + "="*50)
print("📋 MEMORY CONTEXT")
print("="*50)
print(agent.memory.get_context_for_vlm())