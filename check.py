import pytesseract
from PIL import Image
import cv2
import numpy as np
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

def detect_ui_regions(image_path):
    """
    Detect UI regions/elements purely from visual features (no text dependency).
    Uses edge detection, color analysis, and contour detection.
    """
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Could not load image: {image_path}")
    
    height, width = image.shape[:2]
    all_elements = []
    
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    
    # ========== 1. Detect Navbar (top region with distinct background) ==========
    # Check top 100 pixels for uniform color regions
    top_region = image[:100, :]
    top_gray = cv2.cvtColor(top_region, cv2.COLOR_BGR2GRAY)
    
    # Find horizontal lines/edges that might indicate navbar boundary
    edges_top = cv2.Canny(top_gray, 30, 100)
    
    # Detect navbar as a full-width element at top
    navbar_detected = False
    for y in range(50, 100):
        if np.sum(edges_top[y, :]) > width * 0.3:  # Horizontal line detected
            all_elements.append({
                'x': 0, 'y': 0, 'width': width, 'height': y + 10,
                'x2': width, 'y2': y + 10,
                'type': 'navbar', 'element_type': 'navbar'
            })
            navbar_detected = True
            break
    
    if not navbar_detected:
        # Default navbar detection
        all_elements.append({
            'x': 0, 'y': 0, 'width': width, 'height': 60,
            'x2': width, 'y2': 60,
            'type': 'navbar', 'element_type': 'navbar'
        })
    
    # ========== 2. Detect Input Fields / Search Bars ==========
    # Look for rectangular regions with specific characteristics:
    # - Rounded corners or borders
    # - Light/white interior
    # - Often at bottom or in middle of screen (but NOT taskbar)
    
    # Edge detection for bordered elements
    edges = cv2.Canny(gray, 50, 150)
    kernel = np.ones((3, 3), np.uint8)
    dilated = cv2.dilate(edges, kernel, iterations=2)
    
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # Exclude taskbar area (Windows taskbar is typically last 50-60 pixels)
    # Also exclude VS Code status bar (additional ~30 pixels)
    # Total exclusion: bottom 100 pixels
    taskbar_threshold = height - 100
    
    for contour in contours:
        area = cv2.contourArea(contour)
        if area > 2000:
            x, y, w, h = cv2.boundingRect(contour)
            aspect_ratio = w / h if h > 0 else 0
            
            # Skip if in taskbar area
            if y > taskbar_threshold:
                continue
            
            # Input fields are typically wide and short (aspect ratio > 3)
            if aspect_ratio > 3 and w > 200 and h > 20 and h < 100:
                # Check if it's in the lower portion of screen (but above taskbar)
                if y > height * 0.6 and y < taskbar_threshold:
                    elem_type = 'input_field'
                else:
                    elem_type = 'text_area'
                
                all_elements.append({
                    'x': x, 'y': y, 'width': w, 'height': h,
                    'x2': x + w, 'y2': y + h,
                    'type': elem_type, 'element_type': elem_type
                })
    
    # ========== 3. Detect Buttons (colored rectangles) ==========
    color_ranges = [
        ('blue_button', [100, 100, 100], [130, 255, 255]),
        ('green_button', [40, 100, 100], [80, 255, 255]),
        ('red_button', [0, 100, 100], [10, 255, 255]),
        ('orange_button', [10, 100, 100], [25, 255, 255]),
        ('purple_button', [130, 100, 100], [160, 255, 255]),
    ]
    
    for elem_type, lower, upper in color_ranges:
        mask = cv2.inRange(hsv, np.array(lower), np.array(upper))
        button_contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for contour in button_contours:
            area = cv2.contourArea(contour)
            if 500 < area < width * height * 0.1:  # Reasonable button size
                x, y, w, h = cv2.boundingRect(contour)
                if w > 30 and h > 20:  # Minimum button size
                    all_elements.append({
                        'x': x, 'y': y, 'width': w, 'height': h,
                        'x2': x + w, 'y2': y + h,
                        'type': 'button', 'element_type': elem_type
                    })
    
    # ========== 4. Detect Panels / Cards / Containers ==========
    # Look for large rectangular regions with borders or distinct backgrounds
    
    # Adaptive threshold to find regions
    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                    cv2.THRESH_BINARY_INV, 21, 5)
    
    # Morphological operations to find larger regions
    kernel_large = np.ones((10, 10), np.uint8)
    morphed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel_large)
    
    panel_contours, _ = cv2.findContours(morphed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    for contour in panel_contours:
        area = cv2.contourArea(contour)
        if area > 5000:
            x, y, w, h = cv2.boundingRect(contour)
            # Filter out full-screen detections and very small ones
            if w < width * 0.95 and h < height * 0.95 and w > 100 and h > 50:
                # Determine panel type based on position
                if y < height * 0.15:
                    elem_type = 'header_panel'
                elif y > height * 0.8:
                    elem_type = 'footer_panel'
                elif x < width * 0.25:
                    elem_type = 'sidebar'
                else:
                    elem_type = 'content_panel'
                
                # Check for duplicates
                is_dup = any(
                    abs(e['x'] - x) < 20 and abs(e['y'] - y) < 20
                    for e in all_elements
                )
                if not is_dup:
                    all_elements.append({
                        'x': x, 'y': y, 'width': w, 'height': h,
                        'x2': x + w, 'y2': y + h,
                        'type': 'panel', 'element_type': elem_type
                    })
    
    # ========== 5. Detect Icons (small square-ish elements) ==========
    for contour in contours:
        area = cv2.contourArea(contour)
        if 200 < area < 5000:
            x, y, w, h = cv2.boundingRect(contour)
            aspect_ratio = w / h if h > 0 else 0
            
            # Icons are typically square-ish (aspect ratio close to 1)
            if 0.7 < aspect_ratio < 1.4 and 15 < w < 80 and 15 < h < 80:
                all_elements.append({
                    'x': x, 'y': y, 'width': w, 'height': h,
                    'x2': x + w, 'y2': y + h,
                    'type': 'icon', 'element_type': 'icon'
                })
    
    return all_elements

def extract_text_from_region(image_path, box):
    """
    Extract text from a specific region of the image using OCR.
    """
    image = cv2.imread(image_path)
    x, y, w, h = box['x'], box['y'], box['width'], box['height']
    
    # Add padding
    padding = 5
    x1 = max(0, x - padding)
    y1 = max(0, y - padding)
    x2 = min(image.shape[1], x + w + padding)
    y2 = min(image.shape[0], y + h + padding)
    
    # Crop region
    region = image[y1:y2, x1:x2]
    
    if region.size == 0:
        return ""
    
    # Convert to PIL for pytesseract
    region_pil = Image.fromarray(cv2.cvtColor(region, cv2.COLOR_BGR2RGB))
    
    # Extract text
    try:
        text = pytesseract.image_to_string(region_pil, config='--psm 6').strip()
        return text
    except:
        return ""

def enrich_elements_with_text(image_path, elements):
    """
    For each detected UI element, extract the text content within it.
    """
    enriched = []
    
    for elem in elements:
        elem_copy = elem.copy()
        text = extract_text_from_region(image_path, elem)
        elem_copy['text_content'] = text
        enriched.append(elem_copy)
    
    return enriched

def find_element_by_type(elements, element_type):
    """
    Find elements by their type (navbar, input_field, button, etc.)
    """
    return [e for e in elements if e.get('element_type') == element_type or e.get('type') == element_type]

def find_input_field(elements, screen_height=1080):
    """
    Find the input field / search bar from detected elements.
    Excludes taskbar area and full-width system bars.
    """
    # Filter out elements that are likely taskbar or system bars
    # Windows taskbar + status bars typically occupy bottom 150 pixels
    taskbar_y_threshold = screen_height - 150
    
    def is_valid_input(elem):
        # Exclude full-width elements (likely system bars)
        if elem['width'] > 1800:
            return False
        # Must be well above the taskbar area
        if elem['y'] > taskbar_y_threshold:
            return False
        # Also exclude elements starting too close to bottom
        if elem['y'] + elem['height'] > screen_height - 100:
            return False
        return True
    
    # Look for input_field type first
    input_fields = [e for e in find_element_by_type(elements, 'input_field') if is_valid_input(e)]
    if input_fields:
        # Return the largest one (most likely the main input)
        return max(input_fields, key=lambda e: e['width'] * e['height'])
    
    # Fallback: look for text_area
    text_areas = [e for e in find_element_by_type(elements, 'text_area') if is_valid_input(e)]
    if text_areas:
        return max(text_areas, key=lambda e: e['width'] * e['height'])
    
    # Last resort: find wide element near bottom but above taskbar
    for elem in sorted(elements, key=lambda e: e['y'], reverse=True):
        if elem['width'] > 300 and elem['y'] > 500 and is_valid_input(elem):
            return elem
    
    return None

def show_click_highlight(x, y, duration=5, radius=30):
    """
    Show a red circle highlight at the click position.
    """
    import tkinter as tk
    import threading
    
    def create_highlight():
        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes('-topmost', True)
        root.attributes('-transparentcolor', 'white')
        
        win_size = radius * 2 + 20
        win_x = x - win_size // 2
        win_y = y - win_size // 2
        
        root.geometry(f"{win_size}x{win_size}+{win_x}+{win_y}")
        
        canvas = tk.Canvas(root, width=win_size, height=win_size, 
                          bg='white', highlightthickness=0)
        canvas.pack()
        
        center = win_size // 2
        canvas.create_oval(center - radius, center - radius,
                          center + radius, center + radius,
                          outline='red', width=4)
        
        canvas.create_line(center - 10, center, center + 10, center, 
                          fill='red', width=3)
        canvas.create_line(center, center - 10, center, center + 10, 
                          fill='red', width=3)
        
        def pulse(step=0):
            if step < 10:
                new_radius = radius + (5 if step % 2 == 0 else 0)
                canvas.delete("pulse")
                canvas.create_oval(center - new_radius, center - new_radius,
                                  center + new_radius, center + new_radius,
                                  outline='red', width=3, tags="pulse")
                root.after(500, lambda: pulse(step + 1))
        
        pulse()
        root.after(int(duration * 1000), root.destroy)
        
        try:
            root.mainloop()
        except:
            pass
    
    highlight_thread = threading.Thread(target=create_highlight, daemon=True)
    highlight_thread.start()
    return highlight_thread

def click_on_element(box, show_highlight=True):
    """
    Click on the center of a detected element.
    """
    if box is None:
        print("❌ No element to click on!")
        return False
    
    center_x = box['x'] + box['width'] // 2
    center_y = box['y'] + box['height'] // 2
    
    print(f"🖱️ Clicking at coordinates: ({center_x}, {center_y})")
    
    pyautogui.moveTo(center_x, center_y, duration=0.3)
    time.sleep(0.1)
    pyautogui.click()
    
    print(f"✅ Clicked on element at ({center_x}, {center_y})")
    
    if show_highlight:
        print("🔴 Showing red highlight for 5 seconds...")
        highlight_thread = show_click_highlight(center_x, center_y, duration=5)
        highlight_thread.join()
        print("✅ Highlight complete")
    
    return True

def visualize_elements(image_path, elements, output_path='detected_elements.png'):
    """
    Draw detected UI elements on the image with labels.
    """
    image = cv2.imread(image_path)
    
    color_map = {
        'navbar': (255, 165, 0),       # Orange
        'input_field': (0, 255, 0),    # Green
        'text_area': (0, 200, 0),      # Dark Green
        'button': (255, 0, 0),         # Blue
        'blue_button': (255, 0, 0),
        'green_button': (0, 255, 0),
        'red_button': (0, 0, 255),
        'orange_button': (0, 165, 255),
        'purple_button': (255, 0, 255),
        'panel': (255, 255, 0),        # Cyan
        'header_panel': (255, 200, 0),
        'footer_panel': (200, 255, 0),
        'sidebar': (0, 255, 255),      # Yellow
        'content_panel': (255, 255, 100),
        'icon': (128, 128, 255),       # Light red
    }
    
    for i, elem in enumerate(elements):
        x, y, w, h = elem['x'], elem['y'], elem['width'], elem['height']
        elem_type = elem.get('element_type', elem.get('type', 'unknown'))
        color = color_map.get(elem_type, (0, 255, 0))
        
        cv2.rectangle(image, (x, y), (x + w, y + h), color, 2)
        
        # Label with type and text content
        label = f"{i+1}: {elem_type}"
        text_content = elem.get('text_content', '')
        if text_content:
            # Show first 20 chars of text
            short_text = text_content.replace('\n', ' ')[:20]
            label += f" [{short_text}]"
        
        # Draw label background
        (label_w, label_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
        cv2.rectangle(image, (x, y - label_h - 5), (x + min(label_w, 300), y), color, -1)
        cv2.putText(image, label[:50], (x, y - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
    
    cv2.imwrite(output_path, image)
    print(f"✅ Visualization saved to: {output_path}")

if __name__ == "__main__":
    # Take a screenshot
    print("=" * 60)
    print("📸 CAPTURING SCREENSHOT...")
    print("=" * 60)
    
    time.sleep(1)
    screenshot = pyautogui.screenshot()
    image_path = "live_screenshot.png"
    screenshot.save(image_path)
    print(f"✅ Screenshot saved to: {image_path}")
    
    # Detect UI elements visually (no text dependency)
    print("\n" + "=" * 60)
    print("🔍 DETECTING UI ELEMENTS (Visual Detection)")
    print("=" * 60)
    
    elements = detect_ui_regions(image_path)
    
    print(f"\n📊 Detected {len(elements)} UI elements:")
    print("-" * 50)
    
    # Group by type
    by_type = {}
    for elem in elements:
        t = elem.get('element_type', elem.get('type', 'unknown'))
        by_type[t] = by_type.get(t, 0) + 1
    
    for elem_type, count in sorted(by_type.items()):
        print(f"  • {elem_type}: {count}")
    
    # Extract text from each element
    print("\n" + "=" * 60)
    print("📝 EXTRACTING TEXT FROM UI ELEMENTS")
    print("=" * 60)
    
    enriched_elements = enrich_elements_with_text(image_path, elements)
    
    print("\n🔲 UI Elements with Text Content:")
    print("-" * 50)
    for i, elem in enumerate(enriched_elements):
        elem_type = elem.get('element_type', elem.get('type'))
        text = elem.get('text_content', '')
        coords = f"({elem['x']}, {elem['y']}) {elem['width']}x{elem['height']}"
        
        if text:
            text_preview = text.replace('\n', ' ')[:50]
            print(f"  [{i+1}] {elem_type} @ {coords}")
            print(f"       Text: \"{text_preview}\"")
        else:
            print(f"  [{i+1}] {elem_type} @ {coords} (no text)")
    
    # Find and click input field
    print("\n" + "=" * 60)
    print("🔎 FINDING INPUT FIELD / SEARCH BAR")
    print("=" * 60)
    
    input_field = find_input_field(enriched_elements)
    
    if input_field:
        print(f"\n✅ Input field found!")
        print(f"   Type: {input_field.get('element_type', input_field.get('type'))}")
        print(f"   Coordinates: ({input_field['x']}, {input_field['y']}) to ({input_field['x2']}, {input_field['y2']})")
        print(f"   Size: {input_field['width']}x{input_field['height']}")
        if input_field.get('text_content'):
            print(f"   Text: \"{input_field['text_content'][:50]}\"")
        
        # Visualize
        visualize_elements(image_path, enriched_elements, 'detected_elements.png')
        
        # Click
        print("\n🖱️ CLICKING ON INPUT FIELD...")
        print("-" * 50)
        time.sleep(1)
        click_on_element(input_field)
    else:
        print("\n❌ No input field found!")
        visualize_elements(image_path, enriched_elements, 'detected_elements.png')
    
    print("\n" + "=" * 60)
    print("✅ DONE")
    print("=" * 60)