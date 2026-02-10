import pyautogui
import time
import ctypes

# Enable DPI awareness for accurate coordinates on Windows
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor DPI aware
except:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except:
        pass

# Get screen size to verify
screen_width, screen_height = pyautogui.size()
print(f"📺 Screen size: {screen_width}x{screen_height}")

# Get current mouse position for reference
current_x, current_y = pyautogui.position()
print(f"🖱️ Current mouse position: ({current_x}, {current_y})")

# Target coordinates - modify these as needed
x, y = 100,50

print(f"\n🎯 Target coordinates: ({x}, {y})")
print(f"   Moving and clicking in 2 seconds...")

time.sleep(2)
pyautogui.moveTo(x, y, duration=0.5)
time.sleep(0.2)
pyautogui.click()
print(f"✅ Clicked at ({x}, {y})!")

# Show where we ended up
final_x, final_y = pyautogui.position()
print(f"🖱️ Final mouse position: ({final_x}, {final_y})")
