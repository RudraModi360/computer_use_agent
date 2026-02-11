"""
Window Detection Utility
Detects open windows using pygetwindow with OCR fallback
"""

import time
import logging
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


class WindowDetector:
    """Detect and verify open windows"""
    
    def __init__(self):
        self.has_pygetwindow = self._try_import_pygetwindow()
        
    def _try_import_pygetwindow(self) -> bool:
        """Try to import pygetwindow, graceful fallback if unavailable"""
        try:
            global pygetwindow
            import pygetwindow
            logger.info("✓ pygetwindow available for window detection")
            return True
        except ImportError:
            logger.warning("⚠ pygetwindow not available, will use OCR fallback")
            return False
    
    def get_open_windows(self) -> List[str]:
        """
        Get list of all open window titles
        
        Returns:
            List of window title strings
        """
        if not self.has_pygetwindow:
            logger.warning("Window detection unavailable (pygetwindow not installed)")
            return []
        
        try:
            windows = pygetwindow.getAllWindows()
            # Filter out empty or system windows
            titles = [w.title for w in windows if w.title and len(w.title.strip()) > 0]
            return titles
        except Exception as e:
            logger.error(f"Failed to get windows: {e}")
            return []
    
    def is_app_open(self, app_name: str) -> bool:
        """
        Check if an application is open by window title
        
        Args:
            app_name: Application name to search for (e.g., 'Notepad', 'Explorer')
            
        Returns:
            True if window found, False otherwise
        """
        windows = self.get_open_windows()
        search_name = app_name.lower()
        
        for window_title in windows:
            if search_name in window_title.lower():
                logger.info(f"✓ Found window: {window_title}")
                return True
        
        logger.debug(f"✗ App '{app_name}' not found in open windows: {windows}")
        return False
    
    def wait_for_window(self, app_name: str, timeout: float = 5.0, poll_interval: float = 0.3) -> bool:
        """
        Wait for an application window to appear
        
        Args:
            app_name: Application name to wait for
            timeout: Maximum seconds to wait
            poll_interval: How often to check (in seconds)
            
        Returns:
            True if window appeared within timeout, False otherwise
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if self.is_app_open(app_name):
                logger.info(f"✓ Window appeared: {app_name}")
                return True
            
            time.sleep(poll_interval)
        
        logger.error(f"✗ Wait timeout: {app_name} did not appear within {timeout}s")
        return False
    
    def get_window_info(self, app_name: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a specific window
        
        Args:
            app_name: Application name to search for
            
        Returns:
            Dict with window info or None
        """
        if not self.has_pygetwindow:
            return None
        
        try:
            windows = pygetwindow.getWindowsWithTitle(app_name)
            if windows:
                w = windows[0]
                return {
                    "title": w.title,
                    "x": w.left,
                    "y": w.top,
                    "width": w.width,
                    "height": w.height,
                    "isMaximized": w.isMaximized,
                    "isMinimized": w.isMinimized
                }
        except Exception as e:
            logger.debug(f"Failed to get window info: {e}")
        
        return None
    
    def focus_window(self, app_name: str) -> bool:
        """
        Bring a window to focus
        
        Args:
            app_name: Application name to focus
            
        Returns:
            True if successful
        """
        if not self.has_pygetwindow:
            return False
        
        try:
            windows = pygetwindow.getWindowsWithTitle(app_name)
            if windows:
                w = windows[0]
                w.activate()
                time.sleep(0.3)
                return True
        except Exception as e:
            logger.debug(f"Failed to focus window: {e}")
        
        return False


# Global instance
_detector = None

def get_detector() -> WindowDetector:
    """Get or create global window detector instance"""
    global _detector
    if _detector is None:
        _detector = WindowDetector()
    return _detector


def is_app_open(app_name: str) -> bool:
    """Convenience function: check if app is open"""
    return get_detector().is_app_open(app_name)


def wait_for_window(app_name: str, timeout: float = 5.0) -> bool:
    """Convenience function: wait for window to appear"""
    return get_detector().wait_for_window(app_name, timeout)


def get_open_windows() -> List[str]:
    """Convenience function: get all open windows"""
    return get_detector().get_open_windows()
