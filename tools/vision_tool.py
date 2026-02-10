"""Vision Tool - Computer vision with agentic refinement."""
import cv2
import numpy as np
import pyautogui
import time
import os
from typing import List, Dict, Optional, Tuple
from .base_tool import BaseTool, ToolResult

import sys
import ctypes
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from visual_detector import VisualDetector
from annotator import Annotator
import threading
try:
    import tkinter as tk
except ImportError:
    tk = None

# Enable DPI awareness for accurate coordinates on Windows
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except:
        pass


class VisionTool(BaseTool):
    """
    Computer vision tool with agentic refinement.
    Use for: UI navigation, clicking elements, visual analysis.
    """
    
    name = "computer_use"
    description = "Analyze screen, detect UI elements, click on them. Use for UI navigation and interaction."
    
    def __init__(self, output_dir: str = "agent_output"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.detector = VisualDetector(ocr_enabled=True)
        self.annotator = Annotator()
        self._last_elements: List[Dict] = []
        self._last_screenshot: str = None
    
    def execute(self, action: str = "detect", element_id: int = None, 
                direction: str = None, query: str = None) -> ToolResult:
        """
        Execute vision action.
        
        Args:
            action: "detect", "click", "scroll", "find", "refine"
            element_id: Element to click (for action="click")
            direction: Scroll direction (for action="scroll")
            query: Text to find (for action="find")
        """
        start_time = time.time()
        
        try:
            if action == "detect":
                return self._detect(start_time)
            
            elif action == "click":
                return self._click(element_id, start_time)
            
            elif action == "scroll":
                return self._scroll(direction or "down", start_time)
            
            elif action == "find":
                return self._find(query, start_time)
            
            elif action == "refine":
                return self._refine(element_id, start_time)
            
            else:
                return ToolResult(False, None, f"Unknown action: {action}")
                
        except Exception as e:
            return ToolResult(False, None, str(e), time.time() - start_time)
    
    def _detect(self, start_time: float) -> ToolResult:
        """Capture and detect all UI elements."""
        # Capture screenshot
        screenshot = pyautogui.screenshot()
        self._last_screenshot = os.path.join(self.output_dir, f"vision_{int(time.time())}.png")
        screenshot.save(self._last_screenshot)
        
        # Detect elements
        elements = self.detector.detect(self._last_screenshot, selective_ocr=True)
        self._last_elements = [e.to_dict() if hasattr(e, 'to_dict') else e for e in elements]
        
        # Create annotated image
        annotated_path = self._last_screenshot.replace('.png', '_annotated.png')
        self.annotator.annotate(self._last_screenshot, self._last_elements, annotated_path)
        
        # Build element summary (Prioritize interactive elements)
        interactive_types = {'button', 'input_field', 'link', 'checkbox', 'dropdown', 'icon'}
        element_summary = []
        
        # Sort so interactive ones are first
        sorted_elements = sorted(self._last_elements, 
                               key=lambda e: (0 if e['type'] in interactive_types else 1, e['id']))
        
        for e in sorted_elements[:50]:  # Increased to 50
            text = e.get('text', '').strip()
            if text:
                element_summary.append(f"[{e['id']}] {e['type']} - \"{text[:30]}\"")
            else:
                element_summary.append(f"[{e['id']}] {e['type']}")
        
        return ToolResult(
            success=True,
            output={
                "element_count": len(self._last_elements),
                "elements": element_summary,
                "screenshot": self._last_screenshot,
                "annotated": annotated_path
            },
            execution_time=time.time() - start_time,
            metadata={"elements": self._last_elements, "screenshot_path": self._last_screenshot}
        )
    
    def _click(self, element_id: int, start_time: float) -> ToolResult:
        """Click on element by ID."""
        if not self._last_elements:
            # Auto-detect first
            self._detect(start_time)
        
        # Find element
        target = next((e for e in self._last_elements if e.get('id') == element_id), None)
        if not target:
            return ToolResult(False, None, f"Element [{element_id}] not found")
        
        center = target.get('center', (0, 0))
        x, y = center
        
        # Visual feedback
        self._highlight(x, y)
        
        # Click
        pyautogui.moveTo(x, y, duration=0.2)
        time.sleep(0.1)
        pyautogui.click()
        
        return ToolResult(
            success=True,
            output=f"Clicked [{element_id}] ({target.get('type')}) at ({x}, {y})",
            execution_time=time.time() - start_time,
            metadata={"element": target, "clicked_at": (x, y)}
        )

    def _highlight(self, x: int, y: int, duration: float = 1.0):
        """Show prominent visual feedback for clicks (Red Laser Pointer effect)."""
        print(f"   🎯 TARGET: ({x}, {y})")
        if tk is None:
            return
            
        def show():
            try:
                root = tk.Tk()
                root.overrideredirect(True)
                root.attributes('-topmost', True)
                root.attributes('-transparentcolor', 'white')
                # Center the highlight
                size = 100
                root.geometry(f"{size}x{size}+{int(x-size/2)}+{int(y-size/2)}")
                
                canvas = tk.Canvas(root, width=size, height=size, bg='white', highlightthickness=0)
                canvas.pack()
                
                # Draw concentric red circles/crosshair (Laser Target)
                # Outer circle
                canvas.create_oval(10, 10, size-10, size-10, outline='red', width=4)
                # Inner circle
                canvas.create_oval(35, 35, size-35, size-35, outline='red', width=2)
                # Crosshair
                canvas.create_line(size/2, 20, size/2, size-20, fill='red', width=2)
                canvas.create_line(20, size/2, size-20, size/2, fill='red', width=2)
                
                root.after(int(duration * 1000), root.destroy)
                root.mainloop()
            except:
                pass
        
        threading.Thread(target=show, daemon=True).start()
    
    def _scroll(self, direction: str, start_time: float) -> ToolResult:
        """Scroll screen."""
        amount = 3 if direction == "up" else -3
        pyautogui.scroll(amount)
        
        return ToolResult(
            success=True,
            output=f"Scrolled {direction}",
            execution_time=time.time() - start_time
        )
    
    def _find(self, query: str, start_time: float) -> ToolResult:
        """Find element by text content."""
        if not self._last_elements:
            self._detect(start_time)
        
        query_lower = query.lower()
        matches = []
        for e in self._last_elements:
            text = e.get('text', '').lower()
            if query_lower in text:
                matches.append(e)
        
        if matches:
            return ToolResult(
                success=True,
                output={
                    "found": len(matches),
                    "matches": [f"[{m['id']}] {m['type']} - '{m.get('text', '')[:30]}'" for m in matches]
                },
                execution_time=time.time() - start_time,
                metadata={"matches": matches}
            )
        else:
            return ToolResult(
                success=False,
                output=None,
                error=f"No elements found matching '{query}'",
                execution_time=time.time() - start_time
            )
    
    def _refine(self, element_id: int, start_time: float) -> ToolResult:
        """
        Agentic Vision: Crop and re-analyze a region for more detail.
        """
        if not self._last_elements or not self._last_screenshot:
            return ToolResult(False, None, "No previous detection to refine")
        
        # Find element
        target = next((e for e in self._last_elements if e.get('id') == element_id), None)
        if not target:
            return ToolResult(False, None, f"Element [{element_id}] not found")
        
        # Get bounding box with padding
        bbox = target.get('bbox', [0, 0, 100, 100])
        x, y, w, h = bbox
        
        # Load image and crop with padding
        image = cv2.imread(self._last_screenshot)
        img_h, img_w = image.shape[:2]
        
        padding = 50
        x1 = max(0, x - padding)
        y1 = max(0, y - padding)
        x2 = min(img_w, x + w + padding)
        y2 = min(img_h, y + h + padding)
        
        cropped = image[y1:y2, x1:x2]
        
        # Save cropped region
        crop_path = self._last_screenshot.replace('.png', f'_crop_{element_id}.png')
        cv2.imwrite(crop_path, cropped)
        
        # Re-detect on cropped region (higher detail)
        refined = self.detector.detect(crop_path, selective_ocr=False)
        
        # Map IDs and coordinates back to global space
        global_refined = []
        # Prefix refined IDs with 1000 to avoid collision
        start_id = 1000 + (element_id * 10)
        
        for i, elem in enumerate(refined):
            # Translate bbox and center
            ex, ey, ew, eh = elem.bbox
            global_bbox = [ex + x1, ey + y1, ew, eh]
            global_center = [elem.center[0] + x1, elem.center[1] + y1]
            
            # Create a new UIElement or updated dict
            elem_dict = elem.to_dict() if hasattr(elem, 'to_dict') else elem
            elem_dict['id'] = start_id + i
            elem_dict['bbox'] = global_bbox
            elem_dict['center'] = global_center
            elem_dict['text'] = f"[Refined] {elem_dict.get('text', '')}"
            global_refined.append(elem_dict)
        
        # Update last elements to include these
        self._last_elements.extend(global_refined)
        
        # Update annotated image with new elements
        annotated_path = crop_path.replace('.png', '_annotated.png')
        self.annotator.annotate(crop_path, refined, annotated_path)
        
        return ToolResult(
            success=True,
            output={
                "refined_count": len(global_refined),
                "crop_path": crop_path,
                "crop_annotated": annotated_path,
                "region": [x1, y1, x2-x1, y2-y1],
                "new_element_ids": [e['id'] for e in global_refined]
            },
            execution_time=time.time() - start_time,
            metadata={
                "elements": self._last_elements,
                "screenshot_path": crop_path # VLM should see the crop
            }
        )
    
    def get_schema(self):
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "action": {"type": "string", "enum": ["detect", "click", "scroll", "find", "refine"], "required": True},
                "element_id": {"type": "integer", "description": "Element ID to click/refine"},
                "direction": {"type": "string", "enum": ["up", "down"]},
                "query": {"type": "string", "description": "Text to find"}
            }
        }
