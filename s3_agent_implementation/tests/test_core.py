"""
Test script for S3 Agent core components.
Tests LLM engines and MLLM agent functionality.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core import LMMAgent


def test_ollama_engine():
    """Test Ollama engine with a simple query."""
    print("\n" + "="*60)
    print("TEST 1: Ollama Engine")
    print("="*60)
    
    try:
        # Initialize Ollama agent
        engine_params = {
            "engine_type": "ollama",
            "model": "qwen3:0.6b",  # Small fast model
            "base_url": "http://localhost:11434/v1"
        }
        
        print("Initializing Ollama agent...")
        agent = LMMAgent(
            engine_params=engine_params,
            system_prompt="You are a helpful assistant."
        )
        
        print("Sending test message...")
        agent.add_message("What is 2 + 2? Answer in one word.")
        
        response = agent.get_response(temperature=0.0)
        print(f"✅ Response: {response}")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print("Make sure Ollama is running with: ollama serve")
        return False


def test_agent_with_image():
    """Test agent with image input."""
    print("\n" + "="*60)
    print("TEST 2: Agent with Image")
    print("="*60)
    
    try:
        engine_params = {
            "engine_type": "ollama",
            "model": "llava:7b",  # Vision model
            "base_url": "http://localhost:11434/v1"
        }
        
        print("Initializing vision agent...")
        agent = LMMAgent(
            engine_params=engine_params,
            system_prompt="You are a computer vision assistant."
        )
        
        # Create a simple test image
        print("Creating test image...")
        from PIL import Image, ImageDraw
        img = Image.new('RGB', (100, 100), color='red')
        draw = ImageDraw.Draw(img)
        draw.rectangle([10, 10, 90, 90], fill='blue')
        
        # Save temporarily
        img_path = "test_image.png"
        img.save(img_path)
        
        print("Sending image + text...")
        agent.add_message(
            text_content="What colors do you see in this image?",
            image_content=img_path
        )
        
        response = agent.get_response(temperature=0.0)
        print(f"✅ Response: {response}")
        
        # Cleanup
        os.remove(img_path)
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_message_history():
    """Test message history management."""
    print("\n" + "="*60)
    print("TEST 3: Message History")
    print("="*60)
    
    try:
        engine_params = {
            "engine_type": "ollama",
            "model": "qwen3:0.6b",
            "base_url": "http://localhost:11434/v1"
        }
        
        agent = LMMAgent(
            engine_params=engine_params,
            system_prompt="You are a helpful assistant."
        )
        
        print("Adding multiple messages...")
        agent.add_message("My name is Alice.")
        agent.add_message("Hello Alice! How can I help you?", role="assistant")
        agent.add_message("What's my name?")
        
        print(f"Message count: {len(agent.messages)}")
        print(f"Last message role: {agent.messages[-1]['role']}")
        
        response = agent.get_response(temperature=0.0)
        print(f"✅ Response: {response}")
        
        # Test reset
        print("Testing reset...")
        agent.reset()
        print(f"Message count after reset: {len(agent.messages)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("S3 AGENT CORE COMPONENT TESTS")
    print("="*60)
    
    results = []
    
    # Test 1: Basic Ollama
    results.append(("Ollama Engine", test_ollama_engine()))
    
    # Test 2: Vision
    results.append(("Vision Agent", test_agent_with_image()))
    
    # Test 3: History
    results.append(("Message History", test_message_history()))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed!")
    else:
        print("\n⚠️  Some tests failed. Check errors above.")


if __name__ == "__main__":
    main()
