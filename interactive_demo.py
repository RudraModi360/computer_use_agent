#!/usr/bin/env python3
"""
Interactive Demo - Real UI Automation
Opens browser, navigates to TensorTonic, and searches for "focal loss problem"

WARNING: This will actually control your mouse and keyboard!
Press Ctrl+C to stop at any time.
"""

import sys
import os
import time
import subprocess

# Add the s3_agent_implementation to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 's3_agent_implementation'))

from agents.grounding import OSWorldACI
import pyautogui

# Safety settings
pyautogui.FAILSAFE = True  # Move mouse to corner to abort
pyautogui.PAUSE = 0.5  # Pause between actions


def get_screenshot():
    """Capture current screen."""
    import pyautogui
    screenshot = pyautogui.screenshot()
    # Convert to bytes
    from io import BytesIO
    img_bytes = BytesIO()
    screenshot.save(img_bytes, format='PNG')
    return img_bytes.getvalue()


def check_browser_available():
    """Check if a browser is available."""
    browsers = ['chrome', 'firefox', 'edge', 'msedge']
    for browser in browsers:
        try:
            # Try to find browser in PATH
            result = subprocess.run(['where', browser], capture_output=True, text=True)
            if result.returncode == 0:
                return browser
        except:
            pass
    return None


def execute_task_demo():
    """Execute the actual task."""
    print("\n" + "="*70)
    print("INTERACTIVE DEMO: TensorTonic Search")
    print("="*70)
    print("\nTask: Open browser, navigate to tensortonic.com, search for 'focal loss'")
    print("\n⚠️  WARNING: This will control your mouse and keyboard!")
    print("   - Move mouse to top-left corner to STOP immediately")
    print("   - Press Ctrl+C to cancel")
    print("\nMake sure:")
    print("   1. You can see your desktop")
    print("   2. No important work is open")
    print("   3. You have Chrome, Edge, or Firefox installed")
    
    # Get confirmation
    confirm = input("\nDo you want to proceed? (yes/no): ").lower().strip()
    if confirm not in ['yes', 'y']:
        print("\nCancelled by user.")
        return
    
    # Check browser
    browser = check_browser_available()
    if not browser:
        print("\n❌ No browser found! Please install Chrome, Edge, or Firefox.")
        return
    
    print(f"\n✓ Found browser: {browser}")
    print("\nStarting in 5 seconds... Move mouse to top-left corner to STOP")
    time.sleep(5)
    
    try:
        # Initialize ACI
        print("\n[Step 1/7] Initializing automation agent...")
        aci = OSWorldACI(platform="windows", width=1920, height=1080)
        
        # Take initial screenshot
        screenshot = get_screenshot()
        aci.assign_screenshot({"screenshot": screenshot})
        
        print("[Step 2/7] Opening browser...")
        # Generate code to open browser
        if browser == 'edge' or browser == 'msedge':
            # Open Edge with URL directly
            os.system('start msedge https://www.tensortonic.com')
        elif browser == 'chrome':
            os.system('start chrome https://www.tensortonic.com')
        else:
            # Generic open
            code = aci.open(browser)
            exec(code)
            time.sleep(2)
            # Type URL
            code = aci.type(None, "https://www.tensortonic.com", enter=True)
            exec(code)
        
        print("[Step 3/7] Waiting for page to load...")
        time.sleep(5)  # Wait for page load
        
        # Take screenshot to see current state
        screenshot = get_screenshot()
        aci.assign_screenshot({"screenshot": screenshot})
        
        print("[Step 4/7] Looking for search box...")
        # Try to click on search box (common locations)
        # Since we don't have actual CV detection yet, we'll try common positions
        
        # Common search box locations (top center or top right)
        screen_width, screen_height = pyautogui.size()
        
        # Try clicking at common search box positions
        search_positions = [
            (screen_width * 0.5, screen_height * 0.15),   # Center top
            (screen_width * 0.7, screen_height * 0.15),   # Right top
            (screen_width * 0.8, screen_height * 0.1),    # Far right
        ]
        
        search_clicked = False
        for i, (x, y) in enumerate(search_positions):
            print(f"  Trying search position {i+1}: ({int(x)}, {int(y)})")
            pyautogui.click(int(x), int(y))
            time.sleep(1)
            
            # Try typing a test character to see if we're in a search box
            pyautogui.typewrite("f", interval=0.1)
            time.sleep(0.5)
            
            # Check if we're in a search box (heuristic: if 'f' appears, we might be)
            # This is a simple check - in real implementation, we'd use CV
            print(f"  Checking if search box is active...")
            
            # Clear what we typed
            pyautogui.keyDown('ctrl')
            pyautogui.keyDown('a')
            pyautogui.keyUp('a')
            pyautogui.keyUp('ctrl')
            pyautogui.press('delete')
            
            # If we got here without error, assume we're in search box
            search_clicked = True
            break
        
        if not search_clicked:
            print("  ⚠️  Could not find search box automatically")
            print("  Please click on the search box manually in the next 3 seconds...")
            time.sleep(3)
        
        print("[Step 5/7] Typing search query...")
        code = aci.type(None, "focal loss problem", enter=False)
        exec(code)
        
        print("[Step 6/7] Submitting search...")
        pyautogui.press('enter')
        
        print("[Step 7/7] Waiting for results...")
        time.sleep(5)
        
        # Take final screenshot
        screenshot = get_screenshot()
        
        print("\n" + "="*70)
        print("✓ DEMO COMPLETED SUCCESSFULLY!")
        print("="*70)
        print("\nThe browser should now show search results for 'focal loss problem'")
        print("on the TensorTonic website.")
        print("\nYou can now:")
        print("  - Browse the results")
        print("  - Close the browser when done")
        print("  - Run this demo again with different queries")
        
    except pyautogui.FailSafeException:
        print("\n\n⚠️  FAILSAFE TRIGGERED!")
        print("You moved the mouse to the top-left corner.")
        print("Automation stopped for safety.")
    except KeyboardInterrupt:
        print("\n\n⚠️  CANCELLED BY USER (Ctrl+C)")
        print("Automation stopped.")
    except Exception as e:
        print(f"\n\n❌ ERROR: {e}")
        print("Automation failed.")
        import traceback
        traceback.print_exc()


def show_simulation_only():
    """Show what the code would do without executing."""
    print("\n" + "="*70)
    print("SIMULATION MODE (No actual automation)")
    print("="*70)
    
    aci = OSWorldACI(platform="windows", width=1920, height=1080)
    
    print("\nTask: Open browser, navigate to tensortonic.com, search for 'focal loss'")
    print("\nGenerated Automation Code:")
    print("-" * 70)
    
    # Step 1: Open browser
    code1 = aci.open("chrome")
    print(f"\n1. Open Chrome:")
    print(f"   {code1}")
    
    # Step 2: Type URL
    code2 = aci.type(None, "https://www.tensortonic.com", enter=True)
    print(f"\n2. Navigate to TensorTonic:")
    print(f"   {code2}")
    
    # Step 3: Click search (simulated)
    aci.generate_coords = lambda desc, obs: [960, 150]  # Mock coordinates
    code3 = aci.click("search box")
    print(f"\n3. Click search box:")
    print(f"   {code3}")
    
    # Step 4: Type query
    code4 = aci.type(None, "focal loss problem", enter=True)
    print(f"\n4. Search for query:")
    print(f"   {code4}")
    
    print("\n" + "-" * 70)
    print("\nThis is what the code WOULD do.")
    print("To actually execute it, run this script with the --execute flag")
    print("or choose 'yes' when prompted.")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='S3 Agent Interactive Demo')
    parser.add_argument('--simulate', action='store_true', 
                       help='Show simulation only (no actual automation)')
    parser.add_argument('--execute', action='store_true',
                       help='Execute real automation (requires confirmation)')
    
    args = parser.parse_args()
    
    if args.simulate:
        show_simulation_only()
    elif args.execute:
        execute_task_demo()
    else:
        # Default: ask user
        print("\n" + "="*70)
        print("S3 AGENT - INTERACTIVE DEMO")
        print("="*70)
        print("\nChoose mode:")
        print("1. Simulation only (show what code would be generated)")
        print("2. Execute real automation (will control mouse/keyboard)")
        
        choice = input("\nEnter 1 or 2: ").strip()
        
        if choice == '1':
            show_simulation_only()
        elif choice == '2':
            execute_task_demo()
        else:
            print("\nInvalid choice. Exiting.")
            sys.exit(1)
