
import sys
import time
import requests
import subprocess
import atexit
import ollama
import os

from .config import RELAY_BASE_URL, OLLAMA_MODEL
from .telemetry import C
from .browser_tools import _http_session, BrowserTools
from .agent import IntelligentBrowserAgent

# ─────────────────────────────────────────────────────────────────────────────
# Helper: Relay Server Management
# ─────────────────────────────────────────────────────────────────────────────

_relay_process = None

def ensure_relay_server() -> bool:
    """Check if relay server is running, and start it if not."""
    global _relay_process
    
    # Check if already running
    try:
        resp = _http_session.get(f"{RELAY_BASE_URL}/health", timeout=1)
        if resp.status_code == 200:
            return True
    except Exception:
        pass

    # Start it
    print(f"  {C.YELLOW}⚡ Starting relay_server.py...{C.RESET}")
    try:
        # Assuming relay_server.py is in the parent directory of this package
        current_dir = os.path.dirname(os.path.abspath(__file__))
        relay_path = os.path.join(current_dir, "..", "relay_server.py")
        
        # We need to run python
        _relay_process = subprocess.Popen(
            [sys.executable, relay_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=os.path.dirname(relay_path)
        )

        
        # Wait for it to come up
        for i in range(20): # increased wait to 10s
            time.sleep(0.5)
            try:
                resp = _http_session.get(f"{RELAY_BASE_URL}/health", timeout=1)
                if resp.status_code == 200:
                    return True
            except Exception:
                pass
                
    except Exception as e:
        print(f"Failed to start relay: {e}")
        return False
    return False

def cleanup():
    if _relay_process:
        _relay_process.terminate()

atexit.register(cleanup)


def print_help(tools):
    print(f"""
{C.CYAN}{C.BOLD}╔══════════════════════════════════════════════════════════════╗
║         🤖 Intelligent Browser Agent — Commands             ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  Just type your request in natural language!                 ║
║                                                              ║
║  Examples:                                                   ║
║    • "Search Google for weather in Mumbai"                   ║
║    • "Find the GitHub tab and star the repository"           ║
║    • "Click the login button on the active tab"              ║
║    • "Take a screenshot of the current page"                 ║
║    • "Open youtube.com and search for music"                 ║
║                                                              ║
║  Special commands:                                           ║
║    help     — Show this message                              ║
║    tabs     — Quick list of open tabs                        ║
║    quit     — Exit the agent                                 ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝{C.RESET}
""")


def main():
    """Interactive CLI for the intelligent browser agent."""

    print(f"""
{C.CYAN}{C.BOLD}
  ╔══════════════════════════════════════════════════════════════╗
  ║                                                              ║
  ║   🧠  Intelligent Browser Automation Agent                  ║
  ║       with Vision + Auto-Setup                               ║
  ║                                                              ║
  ║   Powered by {OLLAMA_MODEL} via Ollama            ║
  ║   Auto-starts relay • Auto-connects extension               ║
  ║                                                              ║
  ╚══════════════════════════════════════════════════════════════╝
{C.RESET}""")

    # 1. Ensure relay server is running (auto-start if needed)
    relay_was_running = False
    try:
        resp = _http_session.get(f"{RELAY_BASE_URL}/health", timeout=2)
        if resp.status_code == 200:
            relay_was_running = True
            print(f"  {C.GREEN}✓{C.RESET} Relay server: {C.GREEN}already running{C.RESET}")
    except Exception:
        pass

    if not relay_was_running:
        if not ensure_relay_server():
            print(f"  {C.RED}✗{C.RESET} Could not start relay server. Exiting.")
            sys.exit(1)
        else:
             print(f"  {C.GREEN}✓{C.RESET} Relay server: {C.GREEN}started{C.RESET}")

    # 2. Wait for Chrome extension
    ext_connected = False
    try:
        resp = _http_session.get(f"{RELAY_BASE_URL}/health", timeout=2)
        ext_connected = resp.json().get("extension_connected", False)
    except Exception:
        pass

    if not ext_connected:
        print(f"  {C.YELLOW}⏳{C.RESET} Waiting for Chrome extension to auto-connect...")
        for i in range(15):  # 15 seconds max
            time.sleep(1)
            try:
                resp = _http_session.get(f"{RELAY_BASE_URL}/health", timeout=1)
                if resp.json().get("extension_connected", False):
                    ext_connected = True
                    break
            except Exception:
                pass
            spinner = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            print(f"\r    {spinner[i % len(spinner)]} Waiting... ({i+1}s)", end="", flush=True)
        print()

    if ext_connected:
        print(f"  {C.GREEN}✓{C.RESET} Chrome extension: {C.GREEN}connected{C.RESET}")
    else:
        print(f"  {C.YELLOW}⚠{C.RESET} Chrome extension: {C.YELLOW}not connected yet{C.RESET} (will keep trying)")

    # 3. Check Ollama model
    try:
        model_list = ollama.list()
        models = [m.get("model", m.get("name", "")) for m in model_list.get("models", [])]
        if any(OLLAMA_MODEL in m for m in models):
            print(f"  {C.GREEN}✓{C.RESET} VLM model: {C.GREEN}{OLLAMA_MODEL}{C.RESET} (vision enabled)")
        else:
            print(f"  {C.YELLOW}⚠{C.RESET} Model {OLLAMA_MODEL} not found.")
    except Exception as e:
        print(f"  {C.RED}✗{C.RESET} Ollama: {C.RED}not reachable{C.RESET} ({e})")
        sys.exit(1)
    
    # Initialize the Agent
    agent = IntelligentBrowserAgent()
    tools = agent.browser

    print_help(tools)

    while True:
        try:
            prompt = input(f"{C.GREEN}{C.BOLD}🤖 You > {C.RESET}").strip()
            if not prompt:
                continue

            if prompt.lower() in ("quit", "exit", "q"):
                print(f"\n  {C.DIM}Goodbye! 👋{C.RESET}\n")
                break
            elif prompt.lower() == "help":
                print_help(tools)
                continue
            elif prompt.lower() in ("tabs", "list"):
                print(tools.get_all_tabs())
                continue

            # Run the agent
            agent.run_task(prompt)

        except KeyboardInterrupt:
            print(f"\n\n  {C.YELLOW}Interrupted.{C.RESET}\n")
        except EOFError:
            break
        except Exception as e:
            print(f"\n  {C.RED}Error: {e}{C.RESET}\n")


if __name__ == "__main__":
    main()
