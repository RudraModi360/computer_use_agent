"""
Feedback Monitor Module
Detects screen changes and monitors action success for closed-loop control.
"""

import cv2
import numpy as np
import pyautogui
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class FeedbackType(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


@dataclass
class ScreenChange:
    """Detected change between screenshots."""
    has_change: bool
    change_percentage: float
    changed_regions: List[Tuple[int, int, int, int]]
    description: str


@dataclass
class ActionFeedback:
    """Feedback about an executed action."""
    feedback_type: FeedbackType
    screen_change: ScreenChange
    details: str
    confidence: float
    suggestions: List[str]


class FeedbackMonitor:
    """
    Monitors screen changes and provides feedback on action success.
    Enables closed-loop control for the computer use agent.
    """
    
    def __init__(self, change_threshold: float = 0.01, wait_after_action: float = 0.5):
        self.change_threshold = change_threshold
        self.wait_after_action = wait_after_action
        self.previous_screenshot: Optional[np.ndarray] = None
        self.action_history: List[Dict] = []
    
    def capture_baseline(self) -> np.ndarray:
        """Capture current screen as baseline for comparison."""
        screenshot = pyautogui.screenshot()
        self.previous_screenshot = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        return self.previous_screenshot
    
    def detect_changes(self, wait: bool = True) -> ScreenChange:
        """
        Detect changes between current screen and baseline.
        
        Args:
            wait: Whether to wait for UI to update before capturing
        """
        if wait:
            time.sleep(self.wait_after_action)
        
        # Capture current screen
        current = pyautogui.screenshot()
        current_img = cv2.cvtColor(np.array(current), cv2.COLOR_RGB2BGR)
        
        if self.previous_screenshot is None:
            self.previous_screenshot = current_img
            return ScreenChange(False, 0.0, [], "No baseline to compare")
        
        # Resize if dimensions don't match
        if current_img.shape != self.previous_screenshot.shape:
            self.previous_screenshot = current_img
            return ScreenChange(True, 1.0, [], "Screen resolution changed")
        
        # Calculate difference
        diff = cv2.absdiff(current_img, self.previous_screenshot)
        gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray_diff, 30, 255, cv2.THRESH_BINARY)
        
        # Calculate change percentage
        total_pixels = thresh.shape[0] * thresh.shape[1]
        changed_pixels = np.count_nonzero(thresh)
        change_pct = changed_pixels / total_pixels
        
        # Find changed regions
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        changed_regions = []
        for contour in contours:
            if cv2.contourArea(contour) > 100:
                x, y, w, h = cv2.boundingRect(contour)
                changed_regions.append((x, y, w, h))
        
        # Update baseline
        self.previous_screenshot = current_img
        
        has_change = change_pct > self.change_threshold
        description = self._describe_changes(change_pct, changed_regions)
        
        return ScreenChange(has_change, change_pct, changed_regions, description)
    
    def _describe_changes(self, change_pct: float, regions: List) -> str:
        """Generate human-readable description of changes."""
        if change_pct < 0.001:
            return "No visible changes"
        elif change_pct < 0.01:
            return f"Minor changes ({len(regions)} small regions)"
        elif change_pct < 0.05:
            return f"Moderate changes ({len(regions)} regions affected)"
        elif change_pct < 0.2:
            return f"Significant UI update ({change_pct*100:.1f}% changed)"
        else:
            return f"Major screen change ({change_pct*100:.1f}% changed)"
    
    def analyze_action_result(self, action: dict, result, 
                              screen_change: ScreenChange) -> ActionFeedback:
        """
        Analyze action result and provide feedback.
        
        Args:
            action: The action that was executed
            result: ActionResult from executor
            screen_change: Detected screen changes
        """
        action_type = action.get('type', 'unknown')
        suggestions = []
        
        # Analyze based on action type
        if action_type == 'click':
            feedback = self._analyze_click(action, result, screen_change)
        elif action_type == 'type':
            feedback = self._analyze_type(action, result, screen_change)
        elif action_type == 'scroll':
            feedback = self._analyze_scroll(action, result, screen_change)
        else:
            feedback = self._analyze_generic(action, result, screen_change)
        
        # Record in history
        self.action_history.append({
            'action': action,
            'result': result,
            'feedback': feedback,
            'timestamp': time.time()
        })
        
        return feedback
    
    def _analyze_click(self, action, result, change: ScreenChange) -> ActionFeedback:
        """Analyze click action feedback."""
        if not result.success:
            return ActionFeedback(
                FeedbackType.FAILURE, change, 
                f"Click failed: {result.error}",
                0.0, ["Retry click", "Verify element still exists"]
            )
        
        # Successful click should usually cause some change
        if change.has_change:
            if change.change_percentage > 0.05:
                return ActionFeedback(
                    FeedbackType.SUCCESS, change,
                    f"Click triggered UI response: {change.description}",
                    0.9, []
                )
            else:
                return ActionFeedback(
                    FeedbackType.PARTIAL, change,
                    f"Click had minor effect: {change.description}",
                    0.6, ["Check if intended action occurred"]
                )
        else:
            return ActionFeedback(
                FeedbackType.UNKNOWN, change,
                "Click executed but no visible change detected",
                0.3, ["Element may not be interactive", "Try different element"]
            )
    
    def _analyze_type(self, action, result, change: ScreenChange) -> ActionFeedback:
        """Analyze type action feedback."""
        if not result.success:
            return ActionFeedback(
                FeedbackType.FAILURE, change,
                f"Type failed: {result.error}",
                0.0, ["Click input field first", "Check if field is focused"]
            )
        
        # Typing should cause changes in input field region
        if change.has_change:
            return ActionFeedback(
                FeedbackType.SUCCESS, change,
                f"Text appears to have been entered",
                0.8, []
            )
        else:
            return ActionFeedback(
                FeedbackType.UNKNOWN, change,
                "Typed but no visible change (field may not be focused)",
                0.4, ["Click input field first", "Verify text appears"]
            )
    
    def _analyze_scroll(self, action, result, change: ScreenChange) -> ActionFeedback:
        """Analyze scroll action feedback."""
        if change.has_change and change.change_percentage > 0.1:
            return ActionFeedback(
                FeedbackType.SUCCESS, change,
                f"Scroll successful: {change.description}",
                0.9, []
            )
        else:
            return ActionFeedback(
                FeedbackType.PARTIAL, change,
                "Scroll may have reached edge or page is static",
                0.5, ["Try scrolling in opposite direction", "Check if content is scrollable"]
            )
    
    def _analyze_generic(self, action, result, change: ScreenChange) -> ActionFeedback:
        """Generic action analysis."""
        if result.success:
            return ActionFeedback(
                FeedbackType.SUCCESS, change,
                result.details,
                0.7, []
            )
        else:
            return ActionFeedback(
                FeedbackType.FAILURE, change,
                result.details,
                0.0, ["Check action parameters"]
            )
    
    def get_feedback_summary(self) -> str:
        """Generate summary of recent action feedback."""
        if not self.action_history:
            return "No actions recorded"
        
        recent = self.action_history[-5:]
        lines = ["Recent action feedback:"]
        for entry in recent:
            fb = entry['feedback']
            action_type = entry['action'].get('type', '?')
            lines.append(f"  - {action_type}: {fb.feedback_type.value} ({fb.details[:40]})")
        
        return "\n".join(lines)
    
    def should_retry(self, feedback: ActionFeedback) -> bool:
        """Determine if action should be retried based on feedback."""
        return feedback.feedback_type in [FeedbackType.FAILURE, FeedbackType.UNKNOWN]
    
    def clear_history(self):
        """Clear action history."""
        self.action_history = []
        self.previous_screenshot = None
