"""
Vision Module - Computer Vision for S3 Agent
Handles screen capture, element detection, and visual analysis.
"""

import base64
import io
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from PIL import Image
import pyautogui
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class UIElement:
    """Represents a detected UI element."""
    id: int
    element_type: str  # button, input, link, text, etc.
    bbox: Tuple[int, int, int, int]  # x, y, width, height
    center: Tuple[int, int]
    text: str = ""
    confidence: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'type': self.element_type,
            'bbox': self.bbox,
            'center': self.center,
            'text': self.text,
            'confidence': self.confidence
        }


class ScreenshotManager:
    """Manages screenshot capture and processing."""
    
    def __init__(self):
        self.last_screenshot: Optional[Image.Image] = None
        self.last_screenshot_bytes: Optional[bytes] = None
    
    def capture(self) -> Tuple[Image.Image, bytes]:
        """
        Capture current screen.
        
        Returns:
            Tuple of (PIL Image, bytes)
        """
        try:
            screenshot = pyautogui.screenshot()
            self.last_screenshot = screenshot
            
            # Convert to bytes
            img_byte_arr = io.BytesIO()
            screenshot.save(img_byte_arr, format='PNG')
            img_byte_arr.seek(0)
            self.last_screenshot_bytes = img_byte_arr.getvalue()
            
            return screenshot, self.last_screenshot_bytes
        except Exception as e:
            logger.error(f"Failed to capture screenshot: {e}")
            raise
    
    def get_screen_size(self) -> Tuple[int, int]:
        """Get current screen size."""
        return pyautogui.size()
    
    def encode_for_llm(self, image: Image.Image) -> str:
        """Encode image to base64 for LLM consumption."""
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='PNG')
        return base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
    
    def save(self, filepath: str):
        """Save last screenshot to file."""
        if self.last_screenshot:
            self.last_screenshot.save(filepath)
            logger.info(f"Screenshot saved to {filepath}")


class ElementDetector:
    """Detects UI elements on screen using CV and OCR."""
    
    def __init__(self):
        self.elements: List[UIElement] = []
        self.element_counter = 0
    
    def detect_with_ocr(self, image: Image.Image) -> List[UIElement]:
        """
        Detect text elements using OCR.
        
        Args:
            image: PIL Image to analyze
            
        Returns:
            List of UIElement objects
        """
        try:
            import pytesseract
            from pytesseract import Output
            
            # Convert PIL to format tesseract expects
            data = pytesseract.image_to_data(image, output_type=Output.DICT)
            
            elements = []
            for i, text in enumerate(data['text']):
                if text.strip():  # Only keep non-empty text
                    x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
                    
                    element = UIElement(
                        id=self.element_counter,
                        element_type='text',
                        bbox=(x, y, w, h),
                        center=(x + w//2, y + h//2),
                        text=text.strip(),
                        confidence=data['conf'][i] / 100.0
                    )
                    elements.append(element)
                    self.element_counter += 1
            
            self.elements = elements
            logger.info(f"Detected {len(elements)} text elements via OCR")
            return elements
            
        except ImportError:
            logger.warning("pytesseract not installed, OCR unavailable")
            return []
        except Exception as e:
            logger.error(f"OCR detection failed: {e}")
            return []
    
    def detect_with_cv(self, image: Image.Image) -> List[UIElement]:
        """
        Detect UI elements using computer vision (OpenCV).
        
        Args:
            image: PIL Image to analyze
            
        Returns:
            List of UIElement objects
        """
        try:
            import cv2
            
            # Convert PIL to OpenCV format
            img_array = np.array(image)
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            
            elements = []
            
            # Detect buttons (rectangular shapes)
            _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                
                # Filter small elements (noise)
                if w > 30 and h > 15 and w < 400 and h < 150:
                    element = UIElement(
                        id=self.element_counter,
                        element_type='button',
                        bbox=(x, y, w, h),
                        center=(x + w//2, y + h//2),
                        text="",
                        confidence=0.7
                    )
                    elements.append(element)
                    self.element_counter += 1
            
            self.elements.extend(elements)
            logger.info(f"Detected {len(elements)} UI elements via CV")
            return elements
            
        except ImportError:
            logger.warning("OpenCV not installed, CV detection unavailable")
            return []
        except Exception as e:
            logger.error(f"CV detection failed: {e}")
            return []
    
    def find_element_by_text(self, text_query: str) -> Optional[UIElement]:
        """
        Find element by text content.
        
        Args:
            text_query: Text to search for
            
        Returns:
            UIElement or None
        """
        text_query_lower = text_query.lower()
        
        for element in self.elements:
            if text_query_lower in element.text.lower():
                return element
        
        return None
    
    def find_element_by_type(self, element_type: str) -> List[UIElement]:
        """Find all elements of a specific type."""
        return [e for e in self.elements if e.element_type == element_type]
    
    def generate_element_list_text(self) -> str:
        """Generate text list of elements for LLM prompt."""
        lines = ["UI Elements detected on screen:"]
        for elem in self.elements[:50]:  # Limit to 50 elements
            lines.append(f"[{elem.id}] {elem.element_type} at {elem.center} - '{elem.text[:30]}'")
        return "\n".join(lines)


class VisualAnalyzer:
    """Analyzes screenshots using LLM vision capabilities."""
    
    def __init__(self, llm_agent=None):
        self.llm_agent = llm_agent
        self.screenshot_manager = ScreenshotManager()
        self.element_detector = ElementDetector()
    
    def analyze_screen(self, task_description: str = "") -> Dict[str, Any]:
        """
        Perform full screen analysis.
        
        Args:
            task_description: Current task context
            
        Returns:
            Dictionary with analysis results
        """
        # Capture screen
        screenshot, screenshot_bytes = self.screenshot_manager.capture()
        
        # Detect elements
        ocr_elements = self.element_detector.detect_with_ocr(screenshot)
        cv_elements = self.element_detector.detect_with_cv(screenshot)
        
        all_elements = ocr_elements + cv_elements
        
        # Generate analysis
        analysis = {
            'screenshot': screenshot,
            'screenshot_bytes': screenshot_bytes,
            'elements': all_elements,
            'element_count': len(all_elements),
            'screen_size': self.screenshot_manager.get_screen_size(),
            'element_list_text': self.element_detector.generate_element_list_text()
        }
        
        return analysis
    
    def find_element_for_action(self, action_description: str, analysis: Dict) -> Optional[Tuple[int, int]]:
        """
        Find coordinates for an action based on visual analysis.
        
        Args:
            action_description: Natural language description (e.g., "click the search button")
            analysis: Screen analysis results
            
        Returns:
            (x, y) coordinates or None
        """
        # First try exact text match
        element = self.element_detector.find_element_by_text(action_description)
        if element:
            logger.info(f"Found element by text: {element.text} at {element.center}")
            return element.center
        
        # Try partial matches
        words = action_description.lower().split()
        for word in words:
            if len(word) > 3:  # Only try meaningful words
                element = self.element_detector.find_element_by_text(word)
                if element:
                    logger.info(f"Found element by partial match '{word}': {element.text} at {element.center}")
                    return element.center
        
        # Fallback: use LLM if available
        if self.llm_agent:
            return self._query_llm_for_coordinates(action_description, analysis)
        
        return None
    
    def _query_llm_for_coordinates(self, action_description: str, analysis: Dict) -> Optional[Tuple[int, int]]:
        """Query LLM to find coordinates for an action."""
        try:
            prompt = f"""
            You are analyzing a screenshot to find UI elements.
            
            Task: {action_description}
            
            Available UI elements:
            {analysis.get('element_list_text', 'No elements detected')}
            
            Screen size: {analysis.get('screen_size', 'unknown')}
            
            Which element should be clicked? Respond with ONLY the element ID number.
            If no matching element found, respond with "NONE".
            """
            
            # Add screenshot to message
            self.llm_agent.reset()
            self.llm_agent.add_message(
                text_content=prompt,
                image_content=analysis['screenshot_bytes'],
                role="user"
            )
            
            response = self.llm_agent.get_response(temperature=0.0)
            
            # Parse response for element ID
            import re
            numbers = re.findall(r'\d+', response)
            if numbers:
                element_id = int(numbers[0])
                for elem in analysis['elements']:
                    if elem.id == element_id:
                        return elem.center
            
            return None
            
        except Exception as e:
            logger.error(f"LLM coordinate query failed: {e}")
            return None
    
    def wait_for_change(self, timeout: float = 10.0, poll_interval: float = 1.0) -> bool:
        """
        Wait for screen to change.
        
        Args:
            timeout: Maximum time to wait
            poll_interval: Time between checks
            
        Returns:
            True if screen changed, False if timeout
        """
        import time
        
        # Get initial screenshot
        initial, _ = self.screenshot_manager.capture()
        initial_array = np.array(initial)
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            time.sleep(poll_interval)
            
            # Capture new screenshot
            current, _ = self.screenshot_manager.capture()
            current_array = np.array(current)
            
            # Compare
            if initial_array.shape == current_array.shape:
                diff = np.mean(np.abs(initial_array.astype(float) - current_array.astype(float)))
                if diff > 10:  # Threshold for significant change
                    logger.info(f"Screen changed detected (diff: {diff:.2f})")
                    return True
        
        logger.warning("Timeout waiting for screen change")
        return False


# Export main classes
__all__ = [
    'ScreenshotManager',
    'ElementDetector',
    'VisualAnalyzer',
    'UIElement'
]
