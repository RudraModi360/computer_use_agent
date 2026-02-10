from smart_agent import SmartAgent
import time

def main():
    print("🤖 Smart Agent Click Test")
    print("="*50)
    
    # Use fast model
    agent = SmartAgent(
        vlm_model="qwen3:0.6b",
        output_dir="agent_output"
    )
    
    # Task designed to force clicking
    task = "Open Calculator and click the number 7 button"
    
    print(f"🎯 TASK: {task}")
    
    # Run
    results = agent.run(task, max_steps=5)
    
    # Print summary
    print("\n" + "="*50)
    print("📊 SUMMARY")
    print("="*50)
    print(agent.get_summary())

if __name__ == "__main__":
    main()
