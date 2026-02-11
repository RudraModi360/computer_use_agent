#!/usr/bin/env python3
"""
SCENE GRAPH BUILDER - Phase 2 Implementation
Builds structured scene graph from UI elements for LLM consumption
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json


class ElementType(Enum):
    """Types of UI elements"""
    BUTTON = "button"
    INPUT = "input"
    TEXT = "text"
    LINK = "link"
    MENU = "menu"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    DROPDOWN = "dropdown"
    ICON = "icon"
    IMAGE = "image"
    CONTAINER = "container"
    UNKNOWN = "unknown"


@dataclass
class SceneElement:
    """Single element in scene graph"""
    id: int
    element_type: ElementType
    text: str
    bbox: Tuple[int, int, int, int]  # x, y, width, height
    center: Tuple[int, int]
    confidence: float = 1.0
    parent_id: Optional[int] = None
    children_ids: List[int] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'type': self.element_type.value,
            'text': self.text,
            'bbox': self.bbox,
            'center': self.center,
            'confidence': self.confidence,
            'parent': self.parent_id,
            'children': self.children_ids,
            'attributes': self.attributes
        }


@dataclass
class SceneGroup:
    """Group of related elements (e.g., toolbar, form)"""
    id: int
    group_type: str
    element_ids: List[int]
    bbox: Tuple[int, int, int, int]
    label: str = ""
    
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'type': self.group_type,
            'elements': self.element_ids,
            'bbox': self.bbox,
            'label': self.label
        }


@dataclass
class SceneGraph:
    """Complete scene representation"""
    viewport: Dict[str, int]
    elements: List[SceneElement]
    groups: List[SceneGroup]
    relationships: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict:
        return {
            'viewport': self.viewport,
            'elements': [e.to_dict() for e in self.elements],
            'groups': [g.to_dict() for g in self.groups],
            'relationships': self.relationships,
            'metadata': self.metadata
        }
    
    def to_text(self, max_elements: int = 50) -> str:
        """Convert to text format for LLM prompt"""
        lines = [
            f"Screen Size: {self.viewport['width']}x{self.viewport['height']}",
            f"Total Elements: {len(self.elements)}",
            "",
            "Interactive Elements:"
        ]
        
        # Sort by importance (buttons first, then inputs, etc.)
        priority = {
            ElementType.BUTTON: 0,
            ElementType.INPUT: 1,
            ElementType.LINK: 2,
            ElementType.MENU: 3,
            ElementType.CHECKBOX: 4,
            ElementType.DROPDOWN: 5,
            ElementType.TEXT: 6,
            ElementType.UNKNOWN: 7
        }
        
        sorted_elements = sorted(
            self.elements,
            key=lambda e: (priority.get(e.element_type, 99), e.id)
        )[:max_elements]
        
        for elem in sorted_elements:
            text = elem.text[:30] if elem.text else "(no text)"
            lines.append(f"  [{elem.id}] {elem.element_type.value.upper()} \"{text}\" at {elem.center}")
        
        if self.groups:
            lines.extend(["", "Groups:"])
            for group in self.groups[:10]:
                lines.append(f"  {group.group_type}: {group.label} ({len(group.element_ids)} elements)")
        
        return "\n".join(lines)


class SceneGraphBuilder:
    """Builds scene graph from detected UI elements"""
    
    def __init__(self, viewport_width: int = 1920, viewport_height: int = 1080):
        self.viewport = {'width': viewport_width, 'height': viewport_height}
        self.element_counter = 0
        self.group_counter = 0
        
    def build_from_ocr_elements(self, ocr_elements: List[Any]) -> SceneGraph:
        """
        Build scene graph from OCR-detected elements
        
        Args:
            ocr_elements: List of UIElement from vision.detector
            
        Returns:
            SceneGraph with structured elements
        """
        scene_elements = []
        
        for elem in ocr_elements:
            # Determine element type from text and shape
            element_type = self._classify_element(elem)
            
            scene_elem = SceneElement(
                id=self.element_counter,
                element_type=element_type,
                text=elem.text,
                bbox=elem.bbox,
                center=elem.center,
                confidence=getattr(elem, 'confidence', 1.0),
                attributes={
                    'ocr_confidence': getattr(elem, 'confidence', 1.0),
                    'word_num': getattr(elem, 'word_num', 0)
                }
            )
            scene_elements.append(scene_elem)
            self.element_counter += 1
        
        # Build groups
        groups = self._detect_groups(scene_elements)
        
        # Detect relationships
        relationships = self._detect_relationships(scene_elements)
        
        # Build scene graph
        scene = SceneGraph(
            viewport=self.viewport,
            elements=scene_elements,
            groups=groups,
            relationships=relationships,
            metadata={
                'total_elements': len(scene_elements),
                'total_groups': len(groups),
                'build_timestamp': str(__import__('datetime').datetime.now())
            }
        )
        
        return scene
    
    def _classify_element(self, elem: Any) -> ElementType:
        """Classify element type from text and properties"""
        text = elem.text.lower().strip() if elem.text else ""
        
        # Button keywords
        button_keywords = ['button', 'submit', 'ok', 'cancel', 'save', 'delete', 
                          'click', 'apply', 'next', 'back', 'continue', 'login',
                          'sign', 'send', 'search', 'add', 'remove', 'edit', 'new']
        if any(kw in text for kw in button_keywords):
            return ElementType.BUTTON
        
        # Input indicators
        if text in ['email', 'password', 'username', 'search', 'input', 
                   'name', 'phone', 'address'] or '...' in text:
            return ElementType.INPUT
        
        # Link indicators
        if text.startswith('http') or '://' in text or text.endswith('.com'):
            return ElementType.LINK
        
        # Menu indicators
        menu_keywords = ['file', 'edit', 'view', 'help', 'tools', 'options', 
                        'menu', 'settings', 'preferences']
        if text in menu_keywords:
            return ElementType.MENU
        
        # Checkbox indicators
        if text in ['☐', '☑', '☒', '[ ]', '[x]', '[X]']:
            return ElementType.CHECKBOX
        
        # Default to text
        if len(text) > 0:
            return ElementType.TEXT
        
        return ElementType.UNKNOWN
    
    def _detect_groups(self, elements: List[SceneElement]) -> List[SceneGroup]:
        """Detect logical groups of elements"""
        groups = []
        
        # Group by spatial proximity (toolbar detection)
        y_positions = {}
        for elem in elements:
            y = elem.center[1]
            # Round to nearest 50 pixels for grouping
            y_key = (y // 50) * 50
            if y_key not in y_positions:
                y_positions[y_key] = []
            y_positions[y_key].append(elem)
        
        # Create groups for rows with multiple elements
        for y_key, row_elements in y_positions.items():
            if len(row_elements) >= 3:  # At least 3 elements in a row
                # Check if they look like a toolbar or menu bar
                if y_key < 100:  # Top of screen
                    group = SceneGroup(
                        id=self.group_counter,
                        group_type="menubar",
                        element_ids=[e.id for e in row_elements],
                        bbox=self._compute_group_bbox(row_elements),
                        label="Top Menu Bar"
                    )
                    groups.append(group)
                    self.group_counter += 1
        
        # Detect form groups (inputs clustered together)
        inputs = [e for e in elements if e.element_type == ElementType.INPUT]
        if len(inputs) >= 2:
            # Check if they're vertically aligned
            group = SceneGroup(
                id=self.group_counter,
                group_type="form",
                element_ids=[e.id for e in inputs],
                bbox=self._compute_group_bbox(inputs),
                label="Input Form"
            )
            groups.append(group)
            self.group_counter += 1
        
        return groups
    
    def _detect_relationships(self, elements: List[SceneElement]) -> List[Dict]:
        """Detect spatial relationships between elements"""
        relationships = []
        
        for i, elem1 in enumerate(elements):
            for elem2 in elements[i+1:]:
                # Check vertical relationship (above/below)
                y_diff = abs(elem1.center[1] - elem2.center[1])
                x_diff = abs(elem1.center[0] - elem2.center[0])
                
                if y_diff < 30 and x_diff > 50:  # Same row
                    relationships.append({
                        'from': elem1.id,
                        'to': elem2.id,
                        'relation': 'horizontal',
                        'distance': x_diff
                    })
                elif x_diff < 100 and y_diff > 20:  # Same column
                    if elem1.center[1] < elem2.center[1]:
                        relationships.append({
                            'from': elem1.id,
                            'to': elem2.id,
                            'relation': 'above',
                            'distance': y_diff
                        })
                    else:
                        relationships.append({
                            'from': elem2.id,
                            'to': elem1.id,
                            'relation': 'above',
                            'distance': y_diff
                        })
        
        return relationships[:100]  # Limit to avoid too many
    
    def _compute_group_bbox(self, elements: List[SceneElement]) -> Tuple[int, int, int, int]:
        """Compute bounding box for a group of elements"""
        if not elements:
            return (0, 0, 0, 0)
        
        min_x = min(e.bbox[0] for e in elements)
        min_y = min(e.bbox[1] for e in elements)
        max_x = max(e.bbox[0] + e.bbox[2] for e in elements)
        max_y = max(e.bbox[1] + e.bbox[3] for e in elements)
        
        return (min_x, min_y, max_x - min_x, max_y - min_y)


# Quick test
if __name__ == "__main__":
    print("="*60)
    print("SCENE GRAPH BUILDER TEST")
    print("="*60)
    
    from s3_agent.vision import ElementDetector, UIElement
    from PIL import Image, ImageDraw
    
    # Create test image
    img = Image.new('RGB', (800, 600), color='white')
    draw = ImageDraw.Draw(img)
    
    # Draw some UI elements
    draw.rectangle([50, 50, 150, 80], fill='blue')  # Button
    draw.text((70, 58), "Submit", fill='white')
    
    draw.rectangle([200, 50, 350, 80], fill='gray')  # Another button
    draw.text((230, 58), "Cancel", fill='black')
    
    draw.text((50, 150), "Email:", fill='black')  # Label
    draw.rectangle([120, 145, 400, 175], fill='white', outline='blue')  # Input
    
    # Detect elements
    detector = ElementDetector()
    elements = detector.detect_with_ocr(img)
    
    print(f"\nDetected {len(elements)} elements")
    
    # Build scene graph
    builder = SceneGraphBuilder(viewport_width=800, viewport_height=600)
    scene = builder.build_from_ocr_elements(elements)
    
    print(f"\nScene Graph:")
    print(f"  Elements: {len(scene.elements)}")
    print(f"  Groups: {len(scene.groups)}")
    print(f"  Relationships: {len(scene.relationships)}")
    
    print(f"\nText Representation:")
    print("-" * 60)
    print(scene.to_text())
    print("-" * 60)
    
    print("\n✓ Scene Graph Builder working!")
