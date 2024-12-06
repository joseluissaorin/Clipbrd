import os
import sys
import abc
import logging
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class PlatformConfig:
    """Platform-specific configuration."""
    app_name: str = "Clipbrd"
    icon_path: str = ""
    menu_items: Dict[str, Callable] = None
    debug_mode: bool = False

class PlatformInterface(abc.ABC):
    """Abstract base class for platform-specific implementations."""
    
    def __init__(self, config: PlatformConfig):
        self.config = config
        self.setup_logging()
    
    def setup_logging(self) -> None:
        """Setup platform-specific logging."""
        self.logger = logging.getLogger(f"{self.config.app_name}Platform")
        self.logger.setLevel(logging.DEBUG if self.config.debug_mode else logging.INFO)
    
    @abc.abstractmethod
    def initialize(self) -> bool:
        """Initialize platform-specific components."""
        pass
    
    @abc.abstractmethod
    def update_icon(self, text: str, icon_path: Optional[str] = None) -> None:
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
    
    @abc.abstractmethod
    def run(self) -> None:
        """Start the platform-specific event loop."""
        pass
    
    @abc.abstractmethod
    def cleanup(self) -> None:
        """Clean up platform-specific resources."""
        pass

class MacOSPlatform(PlatformInterface):
    """macOS-specific implementation using rumps."""
    
    def __init__(self, config: PlatformConfig):
        super().__init__(config)
        import rumps
        self.rumps = rumps
        self.app = None
    
    def initialize(self) -> bool:
        try:
            self.app = self.rumps.App(self.config.app_name)
            self.setup_menu()
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize macOS platform: {e}")
            return False
    
    def update_icon(self, text: str, icon_path: Optional[str] = None) -> None:
        try:
            if self.app:
                self.app.title = text
                if icon_path and os.path.exists(icon_path):
                    self.app.icon = icon_path
        except Exception as e:
            self.logger.error(f"Failed to update macOS icon: {e}")
    
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

class WindowsPlatform(PlatformInterface):
    """Windows-specific implementation using pystray."""
    
    def __init__(self, config: PlatformConfig):
        super().__init__(config)
        import pystray
        from PIL import Image
        self.pystray = pystray
        self.Image = Image
        self.icon = None
    
    def initialize(self) -> bool:
        try:
            icon_image = self.Image.open(self.config.icon_path) if self.config.icon_path else None
            self.icon = self.pystray.Icon(self.config.app_name, icon_image)
            self.setup_menu()
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize Windows platform: {e}")
            return False
    
    def update_icon(self, text: str, icon_path: Optional[str] = None) -> None:
        try:
            if self.icon:
                if icon_path and os.path.exists(icon_path):
                    self.icon.icon = self.Image.open(icon_path)
                self.icon.title = text
        except Exception as e:
            self.logger.error(f"Failed to update Windows icon: {e}")
    
    def show_notification(self, title: str, message: str) -> None:
        try:
            if self.icon:
                self.icon.notify(title=title, message=message)
        except Exception as e:
            self.logger.error(f"Failed to show Windows notification: {e}")
    
    def setup_menu(self) -> None:
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
    
    def run(self) -> None:
        try:
            if self.icon:
                self.icon.run()
        except Exception as e:
            self.logger.error(f"Failed to run Windows app: {e}")
    
    def cleanup(self) -> None:
        try:
            if self.icon:
                self.icon.stop()
        except Exception as e:
            self.logger.error(f"Failed to cleanup Windows app: {e}")

def create_platform_interface(config: PlatformConfig) -> PlatformInterface:
    """Factory function to create platform-specific interface."""
    if sys.platform == 'darwin':
        return MacOSPlatform(config)
    elif sys.platform == 'win32':
        return WindowsPlatform(config)
    else:
        raise NotImplementedError(f"Platform {sys.platform} is not supported") 