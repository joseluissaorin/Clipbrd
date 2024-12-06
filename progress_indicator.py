import os
import sys
import time
import threading
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum, auto

logger = logging.getLogger(__name__)

class ProgressState(Enum):
    """Progress indicator states."""
    IDLE = auto()
    WORKING = auto()
    SUCCESS = auto()
    ERROR = auto()
    WARNING = auto()

@dataclass
class ProgressInfo:
    """Progress information."""
    message: str
    state: ProgressState
    progress: float = 0.0
    details: Optional[str] = None

class ProgressIndicator:
    """Cross-platform progress indicator."""
    
    def __init__(self, app):
        self.app = app
        self._state = ProgressState.IDLE
        self._message = ""
        self._progress = 0.0
        self._details = None
        self._lock = threading.Lock()
        self._animation_thread = None
        self._stop_animation = threading.Event()
        
        # Platform-specific icons
        self.icons = {
            ProgressState.IDLE: "🔄",
            ProgressState.WORKING: "⚡",
            ProgressState.SUCCESS: "✅",
            ProgressState.ERROR: "❌",
            ProgressState.WARNING: "⚠️"
        }
        
        # Animation frames
        self.animation_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        
    def update(
        self,
        state: ProgressState,
        message: str,
        progress: float = 0.0,
        details: Optional[str] = None
    ) -> None:
        """Update progress indicator."""
        with self._lock:
            self._state = state
            self._message = message
            self._progress = max(0.0, min(1.0, progress))
            self._details = details
            self._update_display()
    
    def _update_display(self) -> None:
        """Update the display based on platform."""
        try:
            if sys.platform == 'darwin':
                self._update_macos_display()
            else:
                self._update_windows_display()
        except Exception as e:
            logger.error(f"Error updating display: {e}")
    
    def _update_macos_display(self) -> None:
        """Update macOS menu bar display."""
        icon = self.icons[self._state]
        if self._state == ProgressState.WORKING:
            # Start animation for working state
            if not self._animation_thread or not self._animation_thread.is_alive():
                self._stop_animation.clear()
                self._animation_thread = threading.Thread(target=self._animate_progress)
                self._animation_thread.daemon = True
                self._animation_thread.start()
        else:
            # Stop animation if running
            if self._animation_thread and self._animation_thread.is_alive():
                self._stop_animation.set()
                self._animation_thread.join()
            
            # Update static display
            display_text = f"Clipbrd: {icon} {self._message}"
            if self._progress > 0:
                display_text += f" ({int(self._progress * 100)}%)"
            self.app.update_icon(display_text)
    
    def _update_windows_display(self) -> None:
        """Update Windows system tray display."""
        icon = self.icons[self._state]
        if self._state == ProgressState.WORKING:
            if not self._animation_thread or not self._animation_thread.is_alive():
                self._stop_animation.clear()
                self._animation_thread = threading.Thread(target=self._animate_progress)
                self._animation_thread.daemon = True
                self._animation_thread.start()
        else:
            if self._animation_thread and self._animation_thread.is_alive():
                self._stop_animation.set()
                self._animation_thread.join()
            
            display_text = f"Clipbrd: {icon} {self._message}"
            if self._progress > 0:
                display_text += f" ({int(self._progress * 100)}%)"
            self.app.update_icon(display_text)
    
    def _animate_progress(self) -> None:
        """Animate progress indicator."""
        frame_index = 0
        while not self._stop_animation.is_set():
            frame = self.animation_frames[frame_index]
            display_text = f"Clipbrd: {frame} {self._message}"
            if self._progress > 0:
                display_text += f" ({int(self._progress * 100)}%)"
            self.app.update_icon(display_text)
            
            frame_index = (frame_index + 1) % len(self.animation_frames)
            time.sleep(0.1)
    
    def start_progress(self, message: str) -> None:
        """Start progress indication."""
        self.update(ProgressState.WORKING, message)
    
    def update_progress(self, progress: float, details: Optional[str] = None) -> None:
        """Update progress value."""
        self.update(ProgressState.WORKING, self._message, progress, details)
    
    def complete_progress(self, message: Optional[str] = None) -> None:
        """Complete progress with success."""
        self.update(ProgressState.SUCCESS, message or "Done")
    
    def error_progress(self, message: str) -> None:
        """Show error in progress."""
        self.update(ProgressState.ERROR, message)
    
    def warning_progress(self, message: str) -> None:
        """Show warning in progress."""
        self.update(ProgressState.WARNING, message)
    
    def reset(self) -> None:
        """Reset progress indicator."""
        self.update(ProgressState.IDLE, "Ready") 