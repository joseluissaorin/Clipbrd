import os
import sys
import abc
import logging
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass
import asyncio
from enum import Enum, auto
import time
import queue
import threading

logger = logging.getLogger(__name__)

class IconState(Enum):
    IDLE = auto()
    WORKING = auto()
    SUCCESS = auto()
    ERROR = auto()
    WARNING = auto()
    SCREENSHOT = auto()
    MCQ_ANSWER = auto()

@dataclass
class PlatformConfig:
    """Platform-specific configuration."""
    app_name: str = "Clipbrd"
    icon_path: str = "assets\icons\clipbrd_windows.ico"
    menu_items: Dict[str, Callable] = None
    debug_mode: bool = False

class PlatformInterface(abc.ABC):
    """Abstract base class for platform-specific implementations."""
    
    def __init__(self, config: PlatformConfig):
        self.config = config
        self.setup_logging()
        self._frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._frame_idx = 0
        self._is_animating = False
        self._running = False
    
    def setup_logging(self) -> None:
        """Setup platform-specific logging."""
        self.logger = logging.getLogger(f"{self.config.app_name}Platform")
        self.logger.setLevel(logging.DEBUG if self.config.debug_mode else logging.INFO)
    
    def get_next_frame(self) -> str:
        """Get next animation frame."""
        frame = self._frames[self._frame_idx]
        self._frame_idx = (self._frame_idx + 1) % len(self._frames)
        return frame
    
    @abc.abstractmethod
    def initialize(self) -> bool:
        """Initialize platform-specific components."""
        pass
    
    @abc.abstractmethod
    def update_icon(self, state: IconState, text: Optional[str] = None) -> None:
        """Update system tray/menu bar icon."""
        pass
    
    @abc.abstractmethod
    def show_notification(self, title: str, message: str) -> None:
        """Show system notification."""
        pass
    
    @abc.abstractmethod
    def setup_menu(self) -> None:
        """Setup system tray/menu bar menu."""
        pass

    def run(self):
        """Run the platform interface synchronously."""
        self._running = True
        try:
            while self._running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.cleanup()

    async def run_async(self):
        """Run the platform interface asynchronously."""
        self._running = True
        try:
            while self._running:
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            self.cleanup()

    def cleanup(self):
        """Cleanup platform resources."""
        self._running = False

class WindowsPlatform(PlatformInterface):
    """Windows-specific implementation using pystray."""
    
    def __init__(self, config: PlatformConfig):
        super().__init__(config)
        import pystray
        from PIL import Image
        import queue
        import threading
        self.pystray = pystray
        self.Image = Image
        self.icon = None
        self.icon_update_queue = queue.Queue()
        self._update_thread = None
        self._icon_states = {
            IconState.IDLE: self.config.icon_path,  # Default Clipbrd icon
            IconState.WORKING: "⚡",
            IconState.SUCCESS: "✅",
            IconState.ERROR: "❌",
            IconState.WARNING: "⚠️",
            IconState.SCREENSHOT: "📸",
            IconState.MCQ_ANSWER: None  # Will be handled specially with text
        }
        self.logger.info("WindowsPlatform initialized")
    
    def initialize(self) -> bool:
        """Initialize Windows platform."""
        try:
            self.logger.info("Initializing Windows platform...")
            # Load the default icon for initialization
            icon_image = self.Image.open(self.config.icon_path)
            self.logger.debug(f"Loaded initial icon from {self.config.icon_path}")
            
            self.icon = self.pystray.Icon(
                self.config.app_name,
                icon_image,
                title=self.config.app_name
            )
            self.logger.debug("Created pystray Icon instance")
            
            self.setup_menu()
            self.logger.debug("Menu setup complete")
            
            # Start the update thread
            self._running = True  # Ensure _running is set before starting thread
            self._update_thread = threading.Thread(target=self._update_loop, daemon=True)
            self._update_thread.start()
            self.logger.info("Update thread started")
            
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize Windows platform: {e}", exc_info=True)
            return False
    
    def _update_loop(self):
        """Background thread to process icon updates."""
        self.logger.info("Icon update loop started")
        import time
        while self._running:
            try:
                if not self.icon_update_queue.empty():
                    state, text = self.icon_update_queue.get_nowait()
                    self.logger.debug(f"Processing icon update: state={state}, text={text}")
                    self._update_icon_image(state, text)
            except Exception as e:
                self.logger.error(f"Error processing icon update: {e}", exc_info=True)
            time.sleep(0.1)  # Check every 100ms
        self.logger.info("Icon update loop ended")
    
    def run(self) -> None:
        """Run Windows system tray. This must be called from the main thread."""
        try:
            self.logger.info("Starting Windows system tray")
            if self.icon:
                self.icon.run()
            else:
                self.logger.error("Icon not initialized before run")
        except Exception as e:
            self.logger.error(f"Failed to run Windows app: {e}", exc_info=True)
    
    def update_icon(self, state: IconState, text: Optional[str] = None) -> None:
        """Queue an icon update to be processed in the main thread."""
        try:
            self.logger.debug(f"Queueing icon update: state={state}, text={text}")
            self.icon_update_queue.put((state, text))
        except Exception as e:
            self.logger.error(f"Failed to queue icon update: {e}", exc_info=True)
    
    def _update_icon_image(self, state: IconState, text: Optional[str] = None) -> None:
        """Update the icon image in the main thread."""
        try:
            self.logger.debug(f"Updating icon image: state={state}, text={text}")
            from utils import create_text_image
            
            if state == IconState.IDLE:
                # For IDLE state, always use the original icon file
                self.logger.debug("Loading IDLE state icon")
                icon_image = self.Image.open(self._icon_states[state])
            elif state == IconState.MCQ_ANSWER and text:
                # For MCQ answers, create image directly from the answer text
                self.logger.debug(f"Creating MCQ answer image with text: {text}")
                icon_image = create_text_image(text)
            else:
                # Handle other states
                if text:
                    # Custom text for any other state
                    self.logger.debug(f"Creating custom text image: {text}")
                    icon_image = create_text_image(text)
                else:
                    # Use the emoji for the state
                    icon_content = self._icon_states[state]
                    self.logger.debug(f"Creating emoji image for state: {icon_content}")
                    icon_image = create_text_image(icon_content)
            
            if self.icon:
                self.logger.debug("Updating icon with new image")
                self.icon.icon = icon_image
                self.logger.debug("Icon update complete")
            else:
                self.logger.error("Icon not initialized for update")
        except Exception as e:
            self.logger.error(f"Failed to update Windows icon: {e}", exc_info=True)
    
    def setup_menu(self) -> None:
        """Setup Windows system tray menu."""
        try:
            if self.icon and self.config.menu_items:
                menu_items = []
                for label, callback in self.config.menu_items.items():
                    menu_items.append(
                        self.pystray.MenuItem(label, callback)
                    )
                self.icon.menu = self.pystray.Menu(*menu_items)
        except Exception as e:
            self.logger.error(f"Failed to setup Windows menu: {e}")
    
    def show_notification(self, title: str, message: str) -> None:
        """Show Windows notification."""
        try:
            if self.icon:
                self.icon.notify(title=title, message=message)
        except Exception as e:
            self.logger.error(f"Failed to show Windows notification: {e}")
    
    def cleanup(self) -> None:
        """Cleanup Windows resources."""
        try:
            self.logger.info("Starting Windows platform cleanup")
            self._running = False
            if self._update_thread and self._update_thread.is_alive():
                self.logger.debug("Waiting for update thread to finish")
                self._update_thread.join(timeout=1.0)
            if self.icon:
                self.logger.debug("Stopping system tray icon")
                self.icon.stop()
            super().cleanup()
            self.logger.info("Windows platform cleanup complete")
        except Exception as e:
            self.logger.error(f"Failed to cleanup Windows app: {e}", exc_info=True)

class MacOSPlatform(PlatformInterface):
    """macOS-specific implementation using rumps."""
    
    def __init__(self, config: PlatformConfig):
        super().__init__(config)
        import rumps
        self.rumps = rumps
        self.app = None
        self._icon_states = {
            IconState.IDLE: "Clipbrd",
            IconState.WORKING: "Clipbrd: {}",  # For animation frames
            IconState.SUCCESS: "Clipbrd: Success!",
            IconState.ERROR: "Clipbrd: ERROR",
            IconState.WARNING: "Clipbrd: Warning",
            IconState.SCREENSHOT: "Clipbrd: Taking screenshot {}",  # For animation frames
            IconState.MCQ_ANSWER: "Clipbrd: {}"
        }
    
    def update_icon(self, state: IconState, text: Optional[str] = None) -> None:
        try:
            if self.app:
                base_text = self._icon_states[state]
                
                if state == IconState.MCQ_ANSWER and text:
                    display_text = base_text.format(text)
                elif text:
                    display_text = f"Clipbrd: {text}"
                elif state in [IconState.WORKING, IconState.SCREENSHOT]:
                    display_text = base_text.format(self.get_next_frame())
                else:
                    display_text = base_text
                
                self.app.title = display_text
        except Exception as e:
            self.logger.error(f"Failed to update macOS icon: {e}")
    
    def initialize(self) -> bool:
        try:
            self.app = self.rumps.App(self.config.app_name)
            self.setup_menu()
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize macOS platform: {e}")
            return False
    
    def show_notification(self, title: str, message: str) -> None:
        try:
            self.rumps.notification(
                title=self.config.app_name,
                subtitle=title,
                message=message
            )
        except Exception as e:
            self.logger.error(f"Failed to show macOS notification: {e}")
    
    def setup_menu(self) -> None:
        try:
            if self.app and self.config.menu_items:
                menu_items = []
                for label, callback in self.config.menu_items.items():
                    menu_items.append(
                        self.rumps.MenuItem(label, callback=callback)
                    )
                self.app.menu = menu_items
        except Exception as e:
            self.logger.error(f"Failed to setup macOS menu: {e}")
    
    def run(self) -> None:
        try:
            if self.app:
                self.app.run()
        except Exception as e:
            self.logger.error(f"Failed to run macOS app: {e}")
    
    def cleanup(self) -> None:
        try:
            if self.app:
                self.rumps.quit_application()
        except Exception as e:
            self.logger.error(f"Failed to cleanup macOS app: {e}")

def create_platform_interface(config: PlatformConfig) -> PlatformInterface:
    """Factory function to create platform-specific interface."""
    if sys.platform == 'darwin':
        return MacOSPlatform(config)
    elif sys.platform == 'win32':
        return WindowsPlatform(config)
    else:
        raise NotImplementedError(f"Platform {sys.platform} is not supported") 