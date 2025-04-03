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
import winsound
from pynput import keyboard
from screenshot import ScreenshotType
from settings_manager import SettingsManager

logger = logging.getLogger(__name__)

class IconState(Enum):
    """Types of icon states available."""
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
    notification_sound: bool = False

class PlatformInterface(abc.ABC):
    """Abstract base class for platform-specific implementations."""
    
    def __init__(self, config: PlatformConfig, settings_manager: SettingsManager):
        self.config = config
        self.settings_manager = settings_manager
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
    
    def __init__(self, config: PlatformConfig, settings_manager: SettingsManager):
        super().__init__(config, settings_manager)
        import pystray
        from PIL import Image
        import queue
        import threading
        import winsound
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
        self.screenshot_callback = None
        self.config.notification_sound = self.settings_manager.get_setting('notification_sound')
        self.notification_sounds = {
            "screenshot": (800, 200),  # Frequency, Duration
            "success": (1000, 200),
            "error": (400, 400)
        }
        self.main_loop = None
        self.logger.info("WindowsPlatform initialized")
    
    def play_sound(self, sound_type: str) -> None:
        """Play a notification sound."""
        try:
            if self.config.notification_sound and sound_type in self.notification_sounds:
                freq, duration = self.notification_sounds[sound_type]
                winsound.Beep(freq, duration)
        except Exception as e:
            self.logger.error(f"Failed to play sound: {e}")
    
    def set_screenshot_callback(self, callback: Callable) -> None:
        """Set the callback for screenshot button."""
        self.screenshot_callback = callback
        self.setup_menu()  # Refresh menu with new callback
        self.logger.debug("Screenshot callback set and menu updated")
    
    def initialize(self) -> bool:
        """Initialize Windows platform."""
        try:
            self.logger.info("Initializing Windows platform...")
            # Store the main event loop
            self.main_loop = asyncio.get_event_loop()
            
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
            
            # Play sound based on state and *current* setting value
            if self.settings_manager.get_setting('notification_sound'):
                if state == IconState.SCREENSHOT: self.play_sound("screenshot")
                elif state == IconState.SUCCESS: self.play_sound("success")
                elif state == IconState.ERROR: self.play_sound("error")
                
        except Exception as e:
            self.logger.error(f"Failed to queue icon update: {e}", exc_info=True)
    
    def _update_icon_image(self, state: IconState, text: Optional[str] = None) -> None:
        """Update the icon image in the main thread, applying theme."""
        try:
            self.logger.debug(f"Updating icon image: state={state}, text={text}")
            from utils import create_text_image
            
            # Get current theme setting
            theme = self.settings_manager.get_setting('theme')
            bg_color = 'black' if theme == 'dark' else 'white'
            text_color = 'white' if theme == 'dark' else 'black'
            self.logger.debug(f"Applying theme: {theme} (bg: {bg_color}, text: {text_color})")

            icon_image = None # Initialize
            if state == IconState.IDLE:
                self.logger.debug("Loading IDLE state icon")
                # For IDLE, load the base icon file. Theme doesn't apply here.
                try:
                    icon_image = self.Image.open(self._icon_states[state])
                except Exception as file_e:
                    logger.error(f"Failed to load IDLE icon file {self._icon_states[state]}: {file_e}")
                    # Fallback to creating a default text image if file load fails
                    icon_image = create_text_image("C", background_color=bg_color, text_color=text_color)

            elif state == IconState.MCQ_ANSWER and text:
                self.logger.debug(f"Creating MCQ answer image with text: {text}")
                icon_image = create_text_image(text, background_color=bg_color, text_color=text_color)
            else:
                # Handle other states (WORKING, SUCCESS, ERROR, etc.)
                icon_content = text if text else self._icon_states.get(state, "?") # Use text if provided, else emoji/fallback
                self.logger.debug(f"Creating text/emoji image for state: {icon_content}")
                icon_image = create_text_image(icon_content, background_color=bg_color, text_color=text_color)

            if self.icon and icon_image:
                self.logger.debug("Updating icon with new image")
                self.icon.icon = icon_image
                # self.icon.update_menu() # Might be needed if menu changes dynamically
                self.logger.debug("Icon update complete")
            elif not self.icon:
                self.logger.error("Icon not initialized for update")
            elif not icon_image:
                self.logger.error(f"Failed to generate icon image for state {state}")

        except Exception as e:
            self.logger.error(f"Failed to update Windows icon: {e}", exc_info=True)
    
    def setup_menu(self) -> None:
        """Setup Windows system tray menu."""
        try:
            if self.icon:
                menu_items = []
                
                # Add screenshot button with proper async handling
                if self.screenshot_callback:
                    menu_items.append(
                        self.pystray.MenuItem(
                            "Take Screenshot",
                            self._handle_screenshot_sync
                        )
                    )
                
                # Add other menu items
                if self.config.menu_items:
                    for label, callback in self.config.menu_items.items():
                        menu_items.append(
                            self.pystray.MenuItem(label, callback)
                        )
                
                self.icon.menu = self.pystray.Menu(*menu_items)
                self.logger.debug("Menu setup completed with screenshot options")
        except Exception as e:
            self.logger.error(f"Failed to setup Windows menu: {e}")
    
    def _handle_screenshot_sync(self, _=None) -> None:
        """Synchronous wrapper for screenshot handling."""
        try:
            if not self.main_loop:
                self.logger.error("Screenshot failed: Main event loop not initialized")
                self.update_icon(IconState.ERROR)
                self.show_notification(
                    "Screenshot Error",
                    "Application not properly initialized"
                )
                return

            self.logger.info("Starting screenshot operation in platform interface")
            # Schedule the coroutine in the main loop
            self.logger.debug("Scheduling screenshot coroutine in main event loop")
            future = asyncio.run_coroutine_threadsafe(
                self._handle_screenshot("full"),
                self.main_loop
            )
            
            # Wait for the result with a timeout
            try:
                self.logger.debug("Waiting for screenshot operation to complete")
                future.result(timeout=10)  # 10 seconds timeout
                self.logger.info("Screenshot operation completed successfully")
            except TimeoutError:
                self.logger.error("Screenshot operation timed out after 10 seconds")
                self.update_icon(IconState.ERROR)
                self.show_notification(
                    "Screenshot Error",
                    "Operation timed out"
                )
                # Return to idle state after error
                self.main_loop.call_soon_threadsafe(
                    lambda: self.update_icon(IconState.IDLE)
                )
            except Exception as e:
                self.logger.error(f"Screenshot operation failed: {e}", exc_info=True)
                self.logger.debug("Operation details:", extra={
                    "has_main_loop": bool(self.main_loop),
                    "has_callback": bool(self.screenshot_callback),
                    "error_type": type(e).__name__
                })
                self.update_icon(IconState.ERROR)
                self.show_notification(
                    "Screenshot Error",
                    f"Failed to take screenshot: {str(e)}"
                )
                # Return to idle state after error
                self.main_loop.call_soon_threadsafe(
                    lambda: self.update_icon(IconState.IDLE)
                )
                
        except Exception as e:
            self.logger.error(f"Error in screenshot handling: {e}", exc_info=True)
            self.update_icon(IconState.ERROR)
            self.show_notification(
                "Screenshot Error",
                f"Failed to take screenshot: {str(e)}"
            )
            # Return to idle state after error
            if self.main_loop:
                self.main_loop.call_soon_threadsafe(
                    lambda: self.update_icon(IconState.IDLE)
                )
            self.logger.info("Screenshot operation completed with errors")
    
    def show_notification(self, title: str, message: str, image: Optional[str] = None) -> None:
        """Show Windows notification with optional image preview."""
        try:
            if self.icon:
                if image:
                    # Convert base64 image to PIL Image for preview
                    import base64
                    import io
                    image_data = base64.b64decode(image)
                    image_preview = self.Image.open(io.BytesIO(image_data))
                    # Resize image for notification
                    image_preview.thumbnail((256, 256))
                    self.icon.notify(title=title, message=message, icon=image_preview)
                else:
                    self.icon.notify(title=title, message=message)
        except Exception as e:
            self.logger.error(f"Failed to show Windows notification: {e}")
    
    async def _handle_screenshot(self, screenshot_type: str) -> None:
        """Handle screenshot action with proper feedback."""
        try:
            self.update_icon(IconState.SCREENSHOT)
            
            if self.screenshot_callback:
                # Create task in the main event loop
                if asyncio.iscoroutinefunction(self.screenshot_callback):
                    await self.screenshot_callback(screenshot_type)
                else:
                    await asyncio.to_thread(self.screenshot_callback, screenshot_type)
                    
                # Only show notification without changing icon state
                self.play_sound("success")
                self.show_notification(
                    "Screenshot Captured",
                    f"{screenshot_type.title()} screenshot taken successfully"
                )
            else:
                self.update_icon(IconState.ERROR)
                self.play_sound("error")
                self.show_notification(
                    "Screenshot Error",
                    "Screenshot functionality not available"
                )
                # Return to idle state after 2 seconds
                await asyncio.sleep(2)
                self.update_icon(IconState.IDLE)
        except Exception as e:
            self.logger.error(f"Screenshot error: {e}")
            self.update_icon(IconState.ERROR)
            self.play_sound("error")
            self.show_notification(
                "Screenshot Error",
                f"Failed to take screenshot: {str(e)}"
            )
            # Return to idle state after 2 seconds
            await asyncio.sleep(2)
            self.update_icon(IconState.IDLE)
    
    def _setup_shortcut(self, shortcut_key: str, screenshot_type: ScreenshotType) -> None:
        """Setup a single keyboard shortcut."""
        try:
            def on_activate():
                # Create task in the event loop
                loop = asyncio.get_event_loop()
                loop.create_task(self._handle_screenshot(screenshot_type))

            hotkey = keyboard.GlobalHotKeys({shortcut_key: on_activate})
            hotkey.start()
            self.hotkey_listeners[shortcut_key] = hotkey
            logger.debug(f"Shortcut {shortcut_key} set up for {screenshot_type.name}")
        except Exception as e:
            logger.error(f"Error setting up shortcut {shortcut_key}: {e}")
    
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
    
    def __init__(self, config: PlatformConfig, settings_manager: SettingsManager):
        super().__init__(config, settings_manager)
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

def create_platform_interface(config: PlatformConfig, settings_manager: SettingsManager) -> PlatformInterface:
    """Factory function to create platform-specific interface."""
    if sys.platform == 'darwin':
        return MacOSPlatform(config, settings_manager)
    elif sys.platform == 'win32':
        return WindowsPlatform(config, settings_manager)
    else:
        raise NotImplementedError(f"Platform {sys.platform} is not supported") 