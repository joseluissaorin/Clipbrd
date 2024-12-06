import asyncio
import logging
from platform_interface import IconState

logger = logging.getLogger(__name__)

class ProgressIndicator:
    def __init__(self, app):
        self.app = app
        self._is_running = False
        self._current_text = None
        self._current_state = IconState.IDLE
        self._task = None
    
    def start(self, text: str = None, state: IconState = IconState.WORKING):
        """Start showing progress animation."""
        self._is_running = True
        self._current_text = text
        self._current_state = state
        if not self._task:
            self._task = asyncio.create_task(self._update_progress())
    
    def stop(self, success: bool = True):
        """Stop showing progress animation."""
        self._is_running = False
        if success:
            self.app.platform.update_icon(IconState.SUCCESS, self._current_text)
        else:
            self.app.platform.update_icon(IconState.ERROR, self._current_text)
        self._current_text = None
        self._current_state = IconState.IDLE
        if self._task:
            self._task.cancel()
            self._task = None
    
    def set_warning(self, text: str = None):
        """Show warning state."""
        self._is_running = False
        self.app.platform.update_icon(IconState.WARNING, text)
        self._current_text = text
        self._current_state = IconState.WARNING
    
    def set_error(self, text: str = None):
        """Show error state."""
        self._is_running = False
        self.app.platform.update_icon(IconState.ERROR, text)
        self._current_text = text
        self._current_state = IconState.ERROR
    
    def set_screenshot(self, text: str = None):
        """Show screenshot state."""
        self._is_running = True
        self._current_text = text
        self._current_state = IconState.SCREENSHOT
        if not self._task:
            self._task = asyncio.create_task(self._update_progress())
    
    def reset(self):
        """Reset to idle state."""
        self._is_running = False
        self.app.platform.update_icon(IconState.IDLE)
        self._current_text = None
        self._current_state = IconState.IDLE
        if self._task:
            self._task.cancel()
            self._task = None
    
    async def _update_progress(self):
        """Update progress animation."""
        try:
            while self._is_running:
                self.app.platform.update_icon(self._current_state, self._current_text)
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error updating progress: {e}") 