import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

try:
    from browser_agent.main import main
    print(f"\n🚀 Launching refactored agent from 'browser_agent' package...\n")
    if __name__ == "__main__":
        main()
except ImportError as e:
    print(f"Error launching browser_agent: {e}")
    print("Ensure you are running from the parent directory or have the package installed.")
    sys.exit(1)
