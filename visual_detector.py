"""
Tier 1: Visual Detector Module
Fast CV-based UI element detection with element hierarchy support.
"""

import cv2
import numpy as np
from PIL import Image
import pytesseract
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import time
import ctypes

# Enable DPI awareness for Windows
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except:
        pass


@dataclass
class UIElement:
    """Represents a detected UI element."""
    id: int
    element_type: str
    bbox: Tuple[int, int, int, int]  # x, y, width, height
    center: Tuple[int, int]
    text: str = ""
    confidence: float = 1.0
    parent_id: Optional[int] = None
    children: List[int] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.element_type,
            "bbox": list(self.bbox),
            "center": list(self.center),
            "text": self.text,
            "confidence": self.confidence,
            "parent_id": self.parent_id,
            "children": self.children
        }


class VisualDetector:
    """
    High-performance visual UI element detector.
    Uses edge detection, color analysis, and contour detection.
    """
    
    def __init__(self, ocr_enabled: bool = True, max_ocr_workers: int = 4):
        self.ocr_enabled = ocr_enabled
        self.max_ocr_workers = max_ocr_workers
        self._element_counter = 0
        
        # Color ranges for button detection (HSV)
        self.button_colors = {
            'blue_button': ([100, 100, 100], [130, 255, 255]),
            'green_button': ([40, 100, 100], [80, 255, 255]),
            'red_button': ([0, 100, 100], [10, 255, 255]),
            'orange_button': ([10, 100, 100], [25, 255, 255]),
            'purple_button': ([130, 100, 100], [160, 255, 255]),
            'cyan_button': ([80, 100, 100], [100, 255, 255]),
        }
    
    def detect(self, image_path: str, selective_ocr: bool = True) -> List[UIElement]:
        """
        Main detection pipeline.
        Returns list of UIElement objects with bounding boxes and types.
        """
        start_time = time.time()
        
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"Could not load image: {image_path}")
        
        height, width = image.shape[:2]
        self._element_counter = 0
        all_elements: List[UIElement] = []
        
        # Preprocess
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        
        # Calculate dynamic thresholds based on resolution
        taskbar_height = int(height * 0.05)  # ~5% of screen height
        navbar_height = int(height * 0.08)   # ~8% of screen height
        min_button_width = int(width * 0.02)  # ~2% of screen width
        
        # Detection pipeline
        all_elements.extend(self._detect_navbar(image, gray, width, navbar_height))
        all_elements.extend(self._detect_input_fields(gray, width, height, taskbar_height))
        all_elements.extend(self._detect_buttons(hsv, width, height, min_button_width))
        all_elements.extend(self._detect_links(image, gray))
        all_elements.extend(self._detect_icons(gray, width, height))
        all_elements.extend(self._detect_panels(gray, width, height))
        all_elements.extend(self._detect_checkboxes(gray))
        all_elements.extend(self._detect_dropdowns(gray, image))
        
        # Remove duplicates and overlapping elements
        all_elements = self._remove_duplicates(all_elements)
        
        # Build hierarchy (which elements are inside which)
        all_elements = self._build_hierarchy(all_elements)
        
        # OCR for text extraction (selective or full)
        if self.ocr_enabled:
            all_elements = self._extract_text_parallel(image_path, all_elements, selective_ocr)
        
        detection_time = time.time() - start_time
        print(f"✅ Detected {len(all_elements)} elements in {detection_time:.2f}s")
        
        return all_elements
    
    def _next_id(self) -> int:
        self._element_counter += 1
        return self._element_counter
    
    def _detect_navbar(self, image: np.ndarray, gray: np.ndarray, 
                       width: int, navbar_height: int) -> List[UIElement]:
        """Detect navigation bar at top of screen."""
        elements = []
        
        top_region = gray[:navbar_height, :]
        edges = cv2.Canny(top_region, 30, 100)
        
        # Look for horizontal line indicating navbar boundary
        for y in range(int(navbar_height * 0.5), navbar_height):
            if np.sum(edges[y, :]) > width * 0.3:
                elements.append(UIElement(
                    id=self._next_id(),
                    element_type="navbar",
                    bbox=(0, 0, width, y + 10),
                    center=(width // 2, (y + 10) // 2)
                ))
                break
        else:
            # Default navbar
            elements.append(UIElement(
                id=self._next_id(),
                element_type="navbar",
                bbox=(0, 0, width, int(navbar_height * 0.75)),
                center=(width // 2, int(navbar_height * 0.375))
            ))
        
        return elements
    
    def _detect_input_fields(self, gray: np.ndarray, width: int, 
                              height: int, taskbar_height: int) -> List[UIElement]:
        """Detect input fields and search bars."""
        elements = []
        
        edges = cv2.Canny(gray, 50, 150)
        kernel = np.ones((3, 3), np.uint8)
        dilated = cv2.dilate(edges, kernel, iterations=2)
        
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        taskbar_y = height - taskbar_height - int(height * 0.05)
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if area > 2000:
                x, y, w, h = cv2.boundingRect(contour)
                aspect_ratio = w / h if h > 0 else 0
                
                # Skip taskbar area
                if y > taskbar_y:
                    continue
                
                # Input fields are wide and short
                if aspect_ratio > 3 and w > int(width * 0.1) and 20 < h < int(height * 0.1):
                    elem_type = 'input_field' if y > height * 0.5 else 'text_area'
                    elements.append(UIElement(
                        id=self._next_id(),
                        element_type=elem_type,
                        bbox=(x, y, w, h),
                        center=(x + w // 2, y + h // 2)
                    ))
        
        return elements
    
    def _detect_buttons(self, hsv: np.ndarray, width: int, height: int,
                        min_width: int) -> List[UIElement]:
        """Detect colored buttons."""
        elements = []
        
        for elem_type, (lower, upper) in self.button_colors.items():
            mask = cv2.inRange(hsv, np.array(lower), np.array(upper))
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            for contour in contours:
                area = cv2.contourArea(contour)
                if 500 < area < width * height * 0.1:
                    x, y, w, h = cv2.boundingRect(contour)
                    if w > min_width and h > 20:
                        elements.append(UIElement(
                            id=self._next_id(),
                            element_type="button",
                            bbox=(x, y, w, h),
                            center=(x + w // 2, y + h // 2)
                        ))
        
        return elements
    
    def _detect_links(self, image: np.ndarray, gray: np.ndarray) -> List[UIElement]:
        """Detect text links (blue/underlined text)."""
        elements = []
        
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        # Blue text (typical link color)
        blue_mask = cv2.inRange(hsv, np.array([100, 50, 50]), np.array([130, 255, 255]))
        
        contours, _ = cv2.findContours(blue_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if 100 < area < 10000:
                x, y, w, h = cv2.boundingRect(contour)
                aspect_ratio = w / h if h > 0 else 0
                # Links are typically wider than tall
                if aspect_ratio > 1.5 and w > 20:
                    elements.append(UIElement(
                        id=self._next_id(),
                        element_type="link",
                        bbox=(x, y, w, h),
                        center=(x + w // 2, y + h // 2)
                    ))
        
        return elements
    
    def _detect_icons(self, gray: np.ndarray, width: int, height: int) -> List[UIElement]:
        """Detect small square-ish icons."""
        elements = []
        
        edges = cv2.Canny(gray, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if 200 < area < 5000:
                x, y, w, h = cv2.boundingRect(contour)
                aspect_ratio = w / h if h > 0 else 0
                
                # Icons are square-ish
                if 0.7 < aspect_ratio < 1.4 and 15 < w < 80 and 15 < h < 80:
                    elements.append(UIElement(
                        id=self._next_id(),
                        element_type="icon",
                        bbox=(x, y, w, h),
                        center=(x + w // 2, y + h // 2)
                    ))
        
        return elements
    
    def _detect_panels(self, gray: np.ndarray, width: int, height: int) -> List[UIElement]:
        """Detect large panels/containers."""
        elements = []
        
        thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                        cv2.THRESH_BINARY_INV, 21, 5)
        kernel = np.ones((10, 10), np.uint8)
        morphed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        
        contours, _ = cv2.findContours(morphed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if area > 5000:
                x, y, w, h = cv2.boundingRect(contour)
                if w < width * 0.95 and h < height * 0.95 and w > 100 and h > 50:
                    # Determine panel type by position
                    if y < height * 0.15:
                        elem_type = 'header_panel'
                    elif y > height * 0.8:
                        elem_type = 'footer_panel'
                    elif x < width * 0.25:
                        elem_type = 'sidebar'
                    else:
                        elem_type = 'content_panel'
                    
                    elements.append(UIElement(
                        id=self._next_id(),
                        element_type=elem_type,
                        bbox=(x, y, w, h),
                        center=(x + w // 2, y + h // 2)
                    ))
        
        return elements
    
    def _detect_checkboxes(self, gray: np.ndarray) -> List[UIElement]:
        """Detect checkbox/radio button elements."""
        elements = []
        
        # Look for small square regions
        edges = cv2.Canny(gray, 100, 200)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if 100 < area < 1000:
                x, y, w, h = cv2.boundingRect(contour)
                aspect_ratio = w / h if h > 0 else 0
                
                # Checkboxes are small squares
                if 0.8 < aspect_ratio < 1.2 and 10 < w < 30 and 10 < h < 30:
                    elements.append(UIElement(
                        id=self._next_id(),
                        element_type="checkbox",
                        bbox=(x, y, w, h),
                        center=(x + w // 2, y + h // 2)
                    ))
        
        return elements
    
    def _detect_dropdowns(self, gray: np.ndarray, image: np.ndarray) -> List[UIElement]:
        """Detect dropdown/select menus (rectangular with arrow indicator)."""
        elements = []
        
        edges = cv2.Canny(gray, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if 1000 < area < 50000:
                x, y, w, h = cv2.boundingRect(contour)
                aspect_ratio = w / h if h > 0 else 0
                
                # Dropdowns are wide, short, with specific proportions
                if 2 < aspect_ratio < 10 and 80 < w < 400 and 20 < h < 60:
                    # Check for arrow indicator on right side
                    right_region = gray[y:y+h, max(0, x+w-30):x+w]
                    if right_region.size > 0:
                        var = np.var(right_region)
                        if var > 500:  # Some visual activity (arrow indicator)
                            elements.append(UIElement(
                                id=self._next_id(),
                                element_type="dropdown",
                                bbox=(x, y, w, h),
                                center=(x + w // 2, y + h // 2)
                            ))
        
        return elements
    
    def _remove_duplicates(self, elements: List[UIElement]) -> List[UIElement]:
        """Remove overlapping/duplicate elements."""
        if not elements:
            return elements
        
        filtered = []
        for elem in elements:
            is_duplicate = False
            for existing in filtered:
                # Check for significant overlap
                x1, y1, w1, h1 = elem.bbox
                x2, y2, w2, h2 = existing.bbox
                
                overlap_x = max(0, min(x1+w1, x2+w2) - max(x1, x2))
                overlap_y = max(0, min(y1+h1, y2+h2) - max(y1, y2))
                overlap_area = overlap_x * overlap_y
                
                elem_area = w1 * h1
                if elem_area > 0 and overlap_area / elem_area > 0.7:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                filtered.append(elem)
        
        return filtered
    
    def _build_hierarchy(self, elements: List[UIElement]) -> List[UIElement]:
        """Establish parent-child relationships based on containment."""
        # Sort by area (largest first for parent detection)
        sorted_elems = sorted(elements, key=lambda e: e.bbox[2] * e.bbox[3], reverse=True)
        
        for i, child in enumerate(sorted_elems):
            cx, cy, cw, ch = child.bbox
            child_center = (cx + cw // 2, cy + ch // 2)
            
            for parent in sorted_elems[:i]:  # Only check larger elements
                px, py, pw, ph = parent.bbox
                
                # Check if child center is inside parent
                if (px < child_center[0] < px + pw and 
                    py < child_center[1] < py + ph):
                    child.parent_id = parent.id
                    parent.children.append(child.id)
                    break
        
        return elements
    
    def _extract_text_parallel(self, image_path: str, elements: List[UIElement],
                                selective: bool = True) -> List[UIElement]:
        """Extract text from elements using parallel OCR."""
        image = cv2.imread(image_path)
        
        # If selective, only OCR elements likely to have text
        text_likely_types = {'button', 'input_field', 'text_area', 'link', 'dropdown', 'navbar'}
        
        elements_to_ocr = []
        for elem in elements:
            if not selective or elem.element_type in text_likely_types:
                elements_to_ocr.append(elem)
        
        # Limit OCR to prevent slowdown
        elements_to_ocr = elements_to_ocr[:15]
        
        def ocr_element(elem: UIElement) -> Tuple[int, str]:
            try:
                x, y, w, h = elem.bbox
                padding = 5
                x1 = max(0, x - padding)
                y1 = max(0, y - padding)
                x2 = min(image.shape[1], x + w + padding)
                y2 = min(image.shape[0], y + h + padding)
                
                region = image[y1:y2, x1:x2]
                if region.size == 0:
                    return (elem.id, "")
                
                region_pil = Image.fromarray(cv2.cvtColor(region, cv2.COLOR_BGR2RGB))
                text = pytesseract.image_to_string(region_pil, config='--psm 6').strip()
                return (elem.id, text)
            except:
                return (elem.id, "")
        
        # Parallel OCR
        with ThreadPoolExecutor(max_workers=self.max_ocr_workers) as executor:
            futures = {executor.submit(ocr_element, elem): elem for elem in elements_to_ocr}
            results = {}
            for future in as_completed(futures):
                elem_id, text = future.result()
                results[elem_id] = text
        
        # Update elements with OCR results
        for elem in elements:
            if elem.id in results:
                elem.text = results[elem.id]
        
        return elements


def detect_elements(image_path: str, ocr: bool = True) -> List[Dict]:
    """
    Convenience function for detecting UI elements.
    Returns list of element dictionaries.
    """
    detector = VisualDetector(ocr_enabled=ocr)
    elements = detector.detect(image_path)
    return [elem.to_dict() for elem in elements]


if __name__ == "__main__":
    import pyautogui
    
    print("📸 Taking screenshot...")
    screenshot = pyautogui.screenshot()
    screenshot.save("test_screenshot.png")
    
    print("🔍 Detecting elements...")
    detector = VisualDetector()
    elements = detector.detect("test_screenshot.png")
    
    print(f"\n📊 Found {len(elements)} elements:")
    for elem in elements:
        print(f"  [{elem.id}] {elem.element_type} @ {elem.center} - '{elem.text[:30]}'" if elem.text else f"  [{elem.id}] {elem.element_type} @ {elem.center}")
