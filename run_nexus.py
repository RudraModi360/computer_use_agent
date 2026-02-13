
import asyncio
import os
import sys

# Ensure we can import from local 'nexus' package
sys.path.append(os.getcwd())

# forcing stdout flush
sys.stdout.reconfigure(encoding='utf-8')

# Move import inside main to show startup message first

def main():
    print("="*60, flush=True)
    print("NEXUS AGENT - MODULAR", flush=True)
    print("="*60, flush=True)
    print("Capabilities:")
    print("1. Native Shell Access (Visible Windows)")
    print("2. Persistent Semantic Memory (RAG + Chunking)")
    print("3. Multi-Provider LLM (Ollama / Llama.cpp)")
    print("="*60, flush=True)

    print("\n[Nexus] Initializing System... (Loading heavy models, please wait)", flush=True)
    
    try:
        from nexus.core.agent import NexusAgent
        agent = NexusAgent()
        
        # Interactive Loop
        print("\n[Nexus] Waiting for command... (Type 'exit' to quit)")
        while True:
            try:
                user_input = input("\nUser > ")
                if user_input.lower() in ['exit', 'quit']:
                    print("[Nexus] Shutting down.")
                    break
                
                if not user_input.strip():
                    continue
                
                print("[Nexus] Thinking...")
                response = agent.chat(user_input)
                
                print(f"\nNexus > {response}")
                
            except KeyboardInterrupt:
                print("\n[Nexus] Interrupted.")
                break
                
    except Exception as e:
        print(f"\n[Fatal Error] {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
