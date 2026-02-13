
import sys
import os
import pickle

# Add current directory to path
sys.path.append(os.getcwd())

from nexus.config import config

def inspect_memory():
    meta_file = os.path.join(config.MEMORY_DIR, "metadata.pkl")
    
    if not os.path.exists(meta_file):
        print("No memory metadata found.")
        return

    try:
        with open(meta_file, "rb") as f:
            metadata = pickle.load(f)
            
        print(f"Total Memories: {len(metadata)}")
        print("-" * 50)
        
        for i, m in enumerate(metadata):
            text = m.get('text', 'N/A')
            print(f"[{i}] {text[:200]}...") # Print first 200 chars
            print("-" * 50)
            
    except Exception as e:
        print(f"Error reading memory: {e}")

if __name__ == "__main__":
    inspect_memory()
