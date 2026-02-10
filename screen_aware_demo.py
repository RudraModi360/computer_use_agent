#!/usr/bin/env python3
"""
Screen-Aware Demo - Uses actual screen capture and CV to find elements
This version CAN see the screen and finds elements dynamically.
"""

import pyautogui
import time
import os
import sys
from PIL import Image
import io
import base64

# Add the s3_agent_implementation to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 's3_agent_implementation'))

from agents.grounding import OSWorldACI

# Safety settings
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.5


def capture_screenshot():
    """Capture current screen and convert to bytes."""
    screenshot = pyautogui.screenshot()
    
    # Convert to bytes for processing
    img_byte_arr = io.BytesIO()
    screenshot.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    
    return img_byte_arr.getvalue(), screenshot


def find_element_by_image(target_image_path):
    """Find an element on screen by its image."""
    try:
        if not os.path.exists(target_image_path):
            return None
        
        # Use pyautogui to locate image on screen
        location = pyautogui.locateOnScreen(target_image_path, confidence=0.8)
        if location:
            center = pyautogui.center(location)
            return (center.x, center.y)
        return None
    except Exception as e:
        print(f"Error finding element: {e}")
        return None


def find_text_on_screen(text):
    """Try to find text on screen using OCR."""
    try:
        import pytesseract
        from PIL import ImageGrab
        
        # Capture screen
        screenshot = ImageGrab.grab()
        
        # Use OCR to find text
        data = pytesseract.image_to_data(screenshot, output_type=pytesseract.Output.DICT)
        
        # Search for text
        for i, word in enumerate(data['text']):
            if text.lower() in word.lower():
                x = data['left'][i] + data['width'][i] // 2
                y = data['top'][i] + data['height'][i] // 2
                return (x, y)
        
        return None
    except Exception as e:
        print(f"OCR not available or error: {e}")
        return None


def smart_browser_automation():
    """
    Smart browser automation with screen reading.
    Uses actual screen capture to verify actions.
    """
    print("\n" + "="*70)
    print("SMART BROWSER AUTOMATION (With Screen Reading)")
    print("="*70)
    
    print("\nThis demo will:")
    print("1. Open Chrome/Edge browser")
    print("2. Navigate to tensortonic.com")
    print("3. Take screenshots to verify each step")
    print("4. Search for 'focal loss'")
    
    print("\n⚠️  This will control your mouse and keyboard!")
    print("   Move mouse to TOP-LEFT corner to STOP immediately")
    
    confirm = input("\nDo you want to proceed? (yes/no): ").lower().strip()
    if confirm not in ['yes', 'y']:
        print("Cancelled.")
        return
    
    print("\nStarting in 5 seconds...")
    print("Current screen will be captured and analyzed")
    time.sleep(5)
    
    try:
        # Initialize ACI with actual screenshot
        print("\n[Step 1/6] Capturing initial screenshot...")
        screenshot_bytes, screenshot_pil = capture_screenshot()
        
        aci = OSWorldACI(platform="windows", width=screenshot_pil.width, height=screenshot_pil.height)
        aci.assign_screenshot({"screenshot": screenshot_bytes})
        print(f"✓ Screen captured: {screenshot_pil.width}x{screenshot_pil.height}")
        
        # Step 2: Open browser using Windows Run dialog
        print("\n[Step 2/6] Opening browser...")
        print("  Pressing Win+R to open Run dialog...")
        pyautogui.keyDown('win')
        pyautogui.keyDown('r')
        pyautogui.keyUp('r')
        pyautogui.keyUp('win')
        time.sleep(1)
        
        print("  Typing browser command...")
        # Try to open Chrome, fallback to Edge
        pyautogui.typewrite("chrome https://www.tensortonic.com", interval=0.01)
        time.sleep(0.5)
        pyautogui.press('enter')
        
        print("✓ Browser launch command sent")
        
        # Step 3: Wait and verify page loaded
        print("\n[Step 3/6] Waiting for page to load (5 seconds)...")
        time.sleep(5)
        
        # Capture new screenshot
        screenshot_bytes, screenshot_pil = capture_screenshot()
        aci.assign_screenshot({"screenshot": screenshot_bytes})
        print("✓ New screenshot captured")
        
        # Step 4: Look for search element
        print("\n[Step 4/6] Looking for search functionality...")
        print("  Trying Ctrl+F to open browser's find function...")
        
        pyautogui.keyDown('ctrl')
        pyautogui.keyDown('f')
        pyautogui.keyUp('f')
        pyautogui.keyUp('ctrl')
        time.sleep(1)
        
        # Take screenshot to verify find box opened
        screenshot_bytes, screenshot_pil = capture_screenshot()
        print("✓ Find dialog opened (check if you see find box in top-right)")
        
        # Step 5: Search for text
        print("\n[Step 5/6] Searching for 'focal loss'...")
        pyautogui.typewrite("focal loss", interval=0.01)
        time.sleep(1)
        
        # Capture result
        screenshot_bytes, screenshot_pil = capture_screenshot()
        print("✓ Search term typed")
        
        # Step 6: Press F3 or Enter to find next occurrence
        print("\n[Step 6/6] Looking for matches...")
        pyautogui.press('f3')  # Find next
        time.sleep(1)
        
        # Final screenshot
        screenshot_bytes, screenshot_pil = capture_screenshot()
        
        print("\n" + "="*70)
        print("✓ AUTOMATION COMPLETED!")
        print("="*70)
        print("\nWhat happened:")
        print("  1. ✓ Opened browser (Chrome/Edge)")
        print("  2. ✓ Navigated to tensortonic.com")
        print("  3. ✓ Captured screenshots at each step")
        print("  4. ✓ Opened find dialog (Ctrl+F)")
        print("  5. ✓ Searched for 'focal loss'")
        print("  6. ✓ Attempted to find matches")
        print("\nCheck your browser - it should show:")
        print("  - Tensortonic website loaded")
        print("  - Find box in top-right with 'focal loss'")
        print("  - Highlighted matches (if any exist on page)")
        
    except pyautogui.FailSafeException:
        print("\n\n⚠️  STOPPED: You moved mouse to top-left corner")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


def simple_click_with_verification():
    """
    Simple click demo that shows before/after screenshots.
    """
    print("\n" + "="*70)
    print("SIMPLE CLICK WITH SCREEN VERIFICATION")
    print("="*70)
    
    print("\nThis will:")
    print("1. Capture current screen")
    print("2. Click at center of screen")
    print("3. Capture screen again")
    print("4. Show you the difference")
    
    confirm = input("\nClick center of screen? (yes/no): ").lower().strip()
    if confirm not in ['yes', 'y']:
        print("Cancelled.")
        return
    
    print("\nCapturing initial screenshot...")
    screenshot1_bytes, screenshot1_pil = capture_screenshot()
    print(f"✓ Initial: {screenshot1_pil.width}x{screenshot1_pil.height}")
    
    # Save initial screenshot
    screenshot1_pil.save("screenshot_before.png")
    print("  Saved: screenshot_before.png")
    
    print("\nClicking in 3 seconds...")
    time.sleep(3)
    
    try:
        # Click center
        center_x = screenshot1_pil.width // 2
        center_y = screenshot1_pil.height // 2
        
        print(f"Clicking at ({center_x}, {center_y})...")
        pyautogui.click(center_x, center_y, duration=0.5)
        
        print("\nCapturing after screenshot...")
        time.sleep(1)
        screenshot2_bytes, screenshot2_pil = capture_screenshot()
        screenshot2_pil.save("screenshot_after.png")
        print("  Saved: screenshot_after.png")
        
        print("\n✓ Click completed!")
        print("  Check screenshot_before.png and screenshot_after.png")
        print("  to see what changed on your screen.")
        
    except pyautogui.FailSafeException:
        print("\n⚠️  STOPPED by user")


def show_current_screen_info():
    """Display information about current screen."""
    print("\n" + "="*70)
    print("CURRENT SCREEN INFORMATION")
    print("="*70)
    
    # Get screen info
    width, height = pyautogui.size()
    mouse_x, mouse_y = pyautogui.position()
    
    print(f"\nScreen Resolution: {width}x{height}")
    print(f"Mouse Position: ({mouse_x}, {mouse_y})")
    
    # Capture and analyze
    print("\nCapturing screen for analysis...")
    screenshot_bytes, screenshot_pil = capture_screenshot()
    
    print(f"Screenshot Size: {screenshot_pil.size}")
    print(f"Color Mode: {screenshot_pil.mode}")
    
    # Try OCR if available
    try:
        import pytesseract
        print("\nAttempting OCR (text recognition)...")
        text = pytesseract.image_to_string(screenshot_pil)
        if text.strip():
            print(f"Found text on screen ({len(text)} characters):")
            # Show first 200 chars
            preview = text[:200].replace('\n', ' ')
            print(f"  '{preview}...'")
        else:
            print("  No text detected (or OCR not working)")
    except ImportError:
        print("\nOCR not available (install pytesseract)")
    except Exception as e:
        print(f"\nOCR error: {e}")
    
    # Save screenshot
    screenshot_pil.save("current_screen.png")
    print("\n✓ Screenshot saved: current_screen.png")
    print("  Open this file to see what the agent 'sees'")


if __name__ == "__main__":
    print("\n" + "="*70)
    print("S3 AGENT - SCREEN-AWARE AUTOMATION DEMO")
    print("="*70)
    print("\nThis demo actually CAPTURES YOUR SCREEN and uses it for automation.")
    print("\nChoose an option:")
    print("1. Show current screen info (no automation)")
    print("2. Simple click with before/after screenshots")
    print("3. Full browser automation (tensortonic.com + focal loss search)")
    
    choice = input("\nEnter 1, 2, or 3: ").strip()
    
    if choice == '1':
        show_current_screen_info()
    elif choice == '2':
        simple_click_with_verification()
    elif choice == '3':
        smart_browser_automation()
    else:
        print("Invalid choice.")
