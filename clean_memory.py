
import sys
import os
import shutil

# Add current directory to path
sys.path.append(os.getcwd())

from nexus.config import config

def clean_memory():
    """Remove existing memory files to start fresh"""
    if os.path.exists(config.MEMORY_DIR):
        print(f"Removing corrupted memory directory: {config.MEMORY_DIR}")
        shutil.rmtree(config.MEMORY_DIR)
        print("Memory cleared. Agent will rebuild index on next start.")
    else:
        print("No memory directory found to clean.")

if __name__ == "__main__":
    clean_memory()
