#!/usr/bin/env python3
"""
Simple Click Demo - TensorTonic Search
Actually clicks on screen at specific coordinates to perform the task.
"""

import pyautogui
import time
import os
import sys

# Safety: Move mouse to top-left corner to stop
pyautogui.FAILSAFE = True

def get_screen_size():
    """Get current screen size."""
    return pyautogui.size()

def demo_click_positions():
    """Demo that shows where clicks will happen before executing."""
    width, height = get_screen_size()
    print(f"\nScreen size: {width}x{height}")
    print("\nPlanned click positions:")
    print(f"  1. Address bar: ({width//2}, 80)")
    print(f"  2. Search box: ({width//2}, {height//4})")
    print(f"  3. (Search will be submitted with Enter key)")
    
    print("\n⚠️  This will:")
    print("   1. Click on your address bar")
    print("   2. Type: tensortonic.com")
    print("   3. Press Enter")
    print("   4. Wait for page to load")
    print("   5. Click on search box")
    print("   6. Type: focal loss problem")
    print("   7. Press Enter")
    
    return width, height

def execute_browser_task():
    """Execute the browser automation task."""
    width, height = demo_click_positions()
    
    confirm = input("\nProceed? (yes/no): ").lower().strip()
    if confirm not in ['yes', 'y']:
        print("Cancelled.")
        return
    
    print("\nStarting in 3 seconds... Move mouse to TOP-LEFT corner to STOP!")
    time.sleep(3)
    
    try:
        print("\n[1/7] Clicking address bar...")
        pyautogui.click(width//2, 80, duration=0.5)
        time.sleep(0.5)
        
        print("[2/7] Typing URL...")
        pyautogui.typewrite("tensortonic.com", interval=0.05)
        time.sleep(0.5)
        
        print("[3/7] Pressing Enter...")
        pyautogui.press('enter')
        time.sleep(5)  # Wait for page to load
        
        print("[4/7] Clicking on page (to focus)...")
        pyautogui.click(width//2, height//3, duration=0.5)
        time.sleep(1)
        
        print("[5/7] Looking for search - trying Ctrl+F first...")
        pyautogui.keyDown('ctrl')
        pyautogui.keyDown('f')
        pyautogui.keyUp('f')
        pyautogui.keyUp('ctrl')
        time.sleep(1)
        
        print("[6/7] Typing 'focal loss' in find box...")
        pyautogui.typewrite("focal loss", interval=0.05)
        time.sleep(2)
        
        print("[7/7] Task completed!")
        print("\n✓ The browser should now highlight 'focal loss' on the page")
        print("  (if it exists on tensortonic.com)")
        
    except pyautogui.FailSafeException:
        print("\n\n⚠️  STOPPED: You moved mouse to top-left corner")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")

def test_simple_click():
    """Test simple clicking at a specific coordinate."""
    print("\n" + "="*60)
    print("SIMPLE CLICK TEST")
    print("="*60)
    print("\nThis will click at a specific point on your screen.")
    print("By default, it will click at the CENTER of your screen.")
    
    width, height = get_screen_size()
    center_x, center_y = width // 2, height // 2
    
    print(f"\nScreen: {width}x{height}")
    print(f"Will click at: ({center_x}, {center_y}) - center of screen")
    
    confirm = input("\nClick center of screen? (yes/no): ").lower().strip()
    if confirm not in ['yes', 'y']:
        print("Cancelled.")
        return
    
    print("\nClicking in 3 seconds... Move mouse to STOP")
    time.sleep(3)
    
    try:
        print(f"Clicking at ({center_x}, {center_y})...")
        pyautogui.click(center_x, center_y, duration=0.5)
        print("✓ Clicked!")
    except pyautogui.FailSafeException:
        print("\n⚠️  STOPPED by user")

if __name__ == "__main__":
    print("\n" + "="*60)
    print("S3 AGENT - CLICK DEMO")
    print("="*60)
    print("\nChoose what to test:")
    print("1. Simple click test (click center of screen)")
    print("2. Full browser task (open tensortonic.com, search focal loss)")
    
    choice = input("\nEnter 1 or 2: ").strip()
    
    if choice == '1':
        test_simple_click()
    elif choice == '2':
        execute_browser_task()
    else:
        print("Invalid choice.")
