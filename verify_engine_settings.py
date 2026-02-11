import sys
import os
import asyncio

# Adjust path
sys.path.append(os.getcwd())

from s3_agent.core.hybrid_engine import HybridVisionEngine

def test_engine():
    print("="*60)
    print("HYBRID ENGINE VERIFICATION")
    print("="*60)
    
    try:
        engine = HybridVisionEngine()
        status = engine.get_status()
        print("\nEngine Status:")
        for key, value in status.items():
            print(f"  {key}: {value}")
        
        # Verify Priority
        if status['current_vision_provider'] == 'groq':
            print("\n✓ Groq is correctly prioritized.")
        else:
            print("\n✗ Groq is NOT prioritized (OpenRouter is active).")
            
        print(f"Reasoning Model: {engine.ollama_model}")
        if engine.ollama_model == 'gpt-oss:20b-cloud':
             print("✓ Reasoning model correctly set to gpt-oss:20b-cloud.")
        else:
             print(f"✗ Reasoning model is {engine.ollama_model}, expected gpt-oss:20b-cloud.")

        print(f"Vision Model (Groq): {engine.groq_model}")
        if engine.groq_model == 'meta-llama/llama-4-scout-17b-16e-instruct':
            print("✓ Vision model correctly set to meta-llama/llama-4-scout-17b-16e-instruct.")
        else:
            print(f"✗ Vision model is {engine.groq_model}, expected meta-llama/llama-4-scout-17b-16e-instruct.")

    except Exception as e:
        print(f"Error during verification: {e}")

if __name__ == "__main__":
    test_engine()
