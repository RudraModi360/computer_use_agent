"""
Image Annotator Module
Draws numbered bounding boxes on screenshots for VLM input.
"""

import cv2
import numpy as np
from typing import List, Dict, Tuple, Union
from dataclasses import dataclass


# Color scheme for element types (BGR)
ELEMENT_COLORS = {
    'navbar': (255, 165, 0),      # Orange
    'input_field': (0, 255, 0),   # Green
    'text_area': (0, 200, 0),     # Dark Green
    'button': (255, 0, 0),        # Blue
    'link': (255, 0, 255),        # Magenta
    'icon': (128, 128, 255),      # Light Red
    'panel': (255, 255, 0),       # Cyan
    'header_panel': (255, 200, 0),
    'footer_panel': (200, 255, 0),
    'sidebar': (0, 255, 255),     # Yellow
    'content_panel': (255, 255, 100),
    'checkbox': (0, 128, 255),    # Orange-ish
    'dropdown': (128, 0, 128),    # Purple
    'default': (0, 255, 0),       # Green fallback
}


class Annotator:
    """
    Annotates screenshots with detected element bounding boxes.
    Produces numbered, color-coded overlays for VLM input.
    """
    
    def __init__(self, 
                 font_scale: float = 0.5,
                 line_thickness: int = 2,
                 show_text_labels: bool = True,
                 show_element_ids: bool = True):
        self.font_scale = font_scale
        self.line_thickness = line_thickness
        self.show_text_labels = show_text_labels
        self.show_element_ids = show_element_ids
        self.font = cv2.FONT_HERSHEY_SIMPLEX
    
    def annotate(self, 
                 image_path: str, 
                 elements: List[Union[Dict, 'UIElement']],
                 output_path: str = None,
                 highlight_element_id: int = None) -> np.ndarray:
        """
        Draw bounding boxes with element IDs on the image.
        
        Args:
            image_path: Path to original screenshot
            elements: List of detected elements (dict or UIElement objects)
            output_path: Optional path to save annotated image
            highlight_element_id: Optional element ID to highlight specially
            
        Returns:
            Annotated image as numpy array
        """
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"Could not load image: {image_path}")
        
        annotated = image.copy()
        
        for elem in elements:
            # Handle both dict and UIElement objects
            if hasattr(elem, 'to_dict'):
                elem = elem.to_dict()
            
            elem_id = elem.get('id', 0)
            elem_type = elem.get('type', elem.get('element_type', 'unknown'))
            bbox = elem.get('bbox', [0, 0, 0, 0])
            text = elem.get('text', '')
            
            x, y, w, h = bbox
            color = ELEMENT_COLORS.get(elem_type, ELEMENT_COLORS['default'])
            
            # Highlight specified element
            thickness = self.line_thickness
            if highlight_element_id is not None and elem_id == highlight_element_id:
                color = (0, 0, 255)  # Red for highlight
                thickness = 4
            
            # Draw bounding box
            cv2.rectangle(annotated, (x, y), (x + w, y + h), color, thickness)
            
            # Draw element ID label
            if self.show_element_ids:
                label = f"[{elem_id}]"
                if self.show_text_labels and text:
                    # Truncate long text
                    short_text = text.replace('\n', ' ')[:15]
                    label += f" {short_text}"
                
                # Label background
                (label_w, label_h), _ = cv2.getTextSize(label, self.font, self.font_scale, 1)
                label_bg_y1 = max(0, y - label_h - 6)
                label_bg_y2 = y
                cv2.rectangle(annotated, (x, label_bg_y1), (x + label_w + 4, label_bg_y2), color, -1)
                
                # Label text
                cv2.putText(annotated, label, (x + 2, y - 4), 
                           self.font, self.font_scale, (0, 0, 0), 1)
            
            # Draw center point
            center = elem.get('center', (x + w // 2, y + h // 2))
            cv2.circle(annotated, tuple(center), 3, color, -1)
        
        if output_path:
            cv2.imwrite(output_path, annotated)
            print(f"✅ Annotated image saved: {output_path}")
        
        return annotated
    
    def create_overlay(self,
                       image_path: str,
                       elements: List[Union[Dict, 'UIElement']],
                       opacity: float = 0.3,
                       output_path: str = None) -> np.ndarray:
        """
        Create a semi-transparent overlay showing element regions.
        Useful for visual debugging.
        """
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"Could not load image: {image_path}")
        
        overlay = image.copy()
        
        for elem in elements:
            if hasattr(elem, 'to_dict'):
                elem = elem.to_dict()
            
            elem_type = elem.get('type', elem.get('element_type', 'unknown'))
            bbox = elem.get('bbox', [0, 0, 0, 0])
            x, y, w, h = bbox
            
            color = ELEMENT_COLORS.get(elem_type, ELEMENT_COLORS['default'])
            
            # Fill with semi-transparent color
            cv2.rectangle(overlay, (x, y), (x + w, y + h), color, -1)
        
        # Blend with original
        result = cv2.addWeighted(image, 1 - opacity, overlay, opacity, 0)
        
        # Add labels on top
        for elem in elements:
            if hasattr(elem, 'to_dict'):
                elem = elem.to_dict()
            
            elem_id = elem.get('id', 0)
            center = elem.get('center', (0, 0))
            
            cv2.putText(result, str(elem_id), tuple(center), 
                       self.font, 0.7, (255, 255, 255), 2)
        
        if output_path:
            cv2.imwrite(output_path, result)
            print(f"✅ Overlay image saved: {output_path}")
        
        return result
    
    def generate_element_list_text(self, elements: List[Union[Dict, 'UIElement']]) -> str:
        """
        Generate a text list of elements for VLM prompt.
        """
        lines = []
        for elem in elements:
            if hasattr(elem, 'to_dict'):
                elem = elem.to_dict()
            
            elem_id = elem.get('id', 0)
            elem_type = elem.get('type', elem.get('element_type', 'unknown'))
            center = elem.get('center', (0, 0))
            text = elem.get('text', '')
            
            if text:
                text_preview = text.replace('\n', ' ')[:30]
                lines.append(f"[{elem_id}] {elem_type} at {tuple(center)} - \"{text_preview}\"")
            else:
                lines.append(f"[{elem_id}] {elem_type} at {tuple(center)}")
        
        return "\n".join(lines)


def annotate_screenshot(image_path: str, elements: List[Dict], 
                        output_path: str = "annotated.png") -> str:
    """
    Convenience function to annotate a screenshot.
    Returns path to annotated image.
    """
    annotator = Annotator()
    annotator.annotate(image_path, elements, output_path)
    return output_path


if __name__ == "__main__":
    # Test with sample data
    sample_elements = [
        {"id": 1, "type": "input_field", "bbox": [100, 200, 300, 40], "center": [250, 220], "text": "Search..."},
        {"id": 2, "type": "button", "bbox": [420, 200, 80, 40], "center": [460, 220], "text": "Go"},
        {"id": 3, "type": "navbar", "bbox": [0, 0, 800, 60], "center": [400, 30], "text": ""},
    ]
    
    print("Testing annotator...")
    annotator = Annotator()
    text_list = annotator.generate_element_list_text(sample_elements)
    print("Element list:")
    print(text_list)
