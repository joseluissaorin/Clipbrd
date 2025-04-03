import os
import sys
import json
import logging
import base64
import io
import threading
from enum import Enum, auto
from typing import Optional, Dict, Callable, Any
from dataclasses import dataclass
from pathlib import Path
from PIL import ImageGrab, Image
from pynput import keyboard

# Configure logging
logger = logging.getLogger(__name__)

class ScreenshotType(Enum):
    """Types of screenshots available."""
    FULL = auto()
    REGION = auto()
    PREDEFINED = auto()
    CUSTOM = auto()

@dataclass
class ScreenshotConfig:
    """Configuration for screenshot functionality."""
    shortcuts: Dict[str, str]
    format: str = "PNG"
    config_dir: Path = Path.home() / ".clipbrd"

class ScreenshotManager:
    """Manages screenshot functionality."""
    
    def __init__(self, config: Optional[ScreenshotConfig] = None):
        self.config = config or self._load_default_config()
        self.hotkey_listeners: Dict[str, keyboard.GlobalHotKeys] = {}
        self.callback: Optional[Callable] = None
        self._screenshot_event = threading.Event()
        self._setup_logging()
        logger.info("Screenshot manager initialized")

    def _setup_logging(self) -> None:
        """Setup logging configuration."""
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    @staticmethod
    def _load_default_config() -> ScreenshotConfig:
        """Load default screenshot configuration."""
        return ScreenshotConfig(
            shortcuts={
                "full_screenshot": "<ctrl>+<shift>+f",
                "region_screenshot": "<ctrl>+<shift>+r",
                "predefined_screenshot": "<ctrl>+<shift>+p",
                "custom_screenshot": "<ctrl>+<shift>+l"
            }
        )

    def initialize(self) -> bool:
        """Initialize the screenshot manager."""
        try:
            # Ensure config directory exists
            self.config.config_dir.mkdir(parents=True, exist_ok=True)
            
            # Load existing shortcuts if available
            self.load_shortcuts()
            
            logger.info("Screenshot manager initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize screenshot manager: {e}")
            return False

    def take_screenshot(self, screenshot_type: ScreenshotType = ScreenshotType.FULL) -> Optional[str]:
        """Take a screenshot and return base64 encoded string."""
        try:
            # For now, always take full screenshot as specified
            screenshot = ImageGrab.grab()
            
            # Convert to base64
            buffered = io.BytesIO()
            screenshot.save(buffered, format=self.config.format)
            buffered.seek(0)
            base64_screenshot = base64.b64encode(buffered.getvalue()).decode('utf-8')
            
            logger.debug("Screenshot captured successfully")
            return base64_screenshot
            
        except Exception as e:
            logger.error(f"Error taking screenshot: {e}")
            return None

    def set_callback(self, callback: Callable[[ScreenshotType], Any]) -> None:
        """Set the callback for screenshot actions."""
        self.callback = callback
        self._setup_shortcuts()
        logger.debug("Screenshot callback set")

    def _setup_shortcuts(self) -> None:
        """Setup keyboard shortcuts."""
        if not self.callback:
            logger.warning("No callback set for shortcuts")
            return

        # Stop existing listeners
        for listener in self.hotkey_listeners.values():
            listener.stop()
        self.hotkey_listeners.clear()

        # Setup new listeners
        for shortcut_name, shortcut_key in self.config.shortcuts.items():
            try:
                screenshot_type = self._get_screenshot_type(shortcut_name)
                if screenshot_type:
                    self._setup_shortcut(shortcut_key, screenshot_type)
            except Exception as e:
                logger.error(f"Error setting up shortcut {shortcut_name}: {e}")

    def _setup_shortcut(self, shortcut_key: str, screenshot_type: ScreenshotType) -> None:
        """Setup a single keyboard shortcut."""
        try:
            def on_activate():
                self._handle_shortcut_sync(screenshot_type)

            hotkey = keyboard.GlobalHotKeys({shortcut_key: on_activate})
            hotkey.start()
            self.hotkey_listeners[shortcut_key] = hotkey
            logger.debug(f"Shortcut {shortcut_key} set up for {screenshot_type.name}")
        except Exception as e:
            logger.error(f"Error setting up shortcut {shortcut_key}: {e}")

    def _handle_shortcut_sync(self, screenshot_type: ScreenshotType) -> None:
        """Handle shortcut activation synchronously."""
        try:
            if self.callback:
                # Create and start worker thread
                worker = threading.Thread(
                    target=self._screenshot_worker,
                    args=(screenshot_type,),
                    daemon=True
                )
                worker.start()
        except Exception as e:
            logger.error(f"Error handling shortcut for {screenshot_type.name}: {e}")

    def _screenshot_worker(self, screenshot_type: ScreenshotType) -> None:
        """Worker thread for taking screenshots."""
        try:
            screenshot_data = self.take_screenshot(screenshot_type)
            if screenshot_data and self.callback:
                self.callback(screenshot_type)
        except Exception as e:
            logger.error(f"Error in screenshot worker: {e}")

    def _get_screenshot_type(self, shortcut_name: str) -> Optional[ScreenshotType]:
        """Get screenshot type from shortcut name."""
        type_map = {
            "full_screenshot": ScreenshotType.FULL,
            "region_screenshot": ScreenshotType.REGION,
            "predefined_screenshot": ScreenshotType.PREDEFINED,
            "custom_screenshot": ScreenshotType.CUSTOM
        }
        return type_map.get(shortcut_name)

    def save_shortcuts(self) -> None:
        """Save shortcuts configuration."""
        config_file = self.config.config_dir / "screenshot_config.json"
        temp_file = config_file.with_suffix('.tmp')
        
        try:
            # Write to temporary file first
            with open(temp_file, 'w') as f:
                json.dump({
                    "shortcuts": self.config.shortcuts,
                    "format": self.config.format
                }, f, indent=2)
            
            # Atomically rename
            temp_file.replace(config_file)
            logger.debug("Shortcuts saved successfully")
        except Exception as e:
            logger.error(f"Error saving shortcuts: {e}")
            if temp_file.exists():
                temp_file.unlink()

    def load_shortcuts(self) -> None:
        """Load shortcuts configuration."""
        config_file = self.config.config_dir / "screenshot_config.json"
        
        try:
            if config_file.exists():
                with open(config_file, 'r') as f:
                    data = json.loads(f.read())
                    self.config.shortcuts.update(data.get("shortcuts", {}))
                    self.config.format = data.get("format", self.config.format)
                logger.debug("Shortcuts loaded successfully")
        except Exception as e:
            logger.error(f"Error loading shortcuts: {e}")

    def cleanup(self) -> None:
        """Cleanup resources."""
        try:
            for listener in self.hotkey_listeners.values():
                listener.stop()
            self.hotkey_listeners.clear()
            logger.debug("Screenshot manager cleaned up")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    

def load_shortcuts() -> Dict[str, str]:
    """Load shortcuts from config file, ensuring defaults exist."""
    config_dir = Path.home() / ".clipbrd"
    config_file = config_dir / "screenshot_config.json"

    default_shortcuts = {
        "full_screenshot": "<ctrl>+<shift>+f",
        "region_screenshot": "<ctrl>+<shift>+r", # Assuming this might exist
        "predefined_screenshot": "<ctrl>+<shift>p", # Assuming this might exist
        "custom_screenshot": "<ctrl>+<shift>+l", # Assuming this might exist
        "reset_icon_shortcut": "<ctrl>+<shift>+i" # Added default reset shortcut
    }

    loaded_shortcuts = {}
    try:
        if config_file.exists():
            with open(config_file, 'r') as f:
                data = json.load(f) # Changed from json.loads(f.read())
                loaded_shortcuts = data.get("shortcuts", {})
        else:
            logger.info("screenshot_config.json not found, using default shortcuts.")
    except Exception as e:
        logger.error(f"Error loading shortcuts from {config_file}: {e}, using defaults.")
        loaded_shortcuts = {} # Reset to empty on error

    # Merge defaults with loaded, prioritizing loaded values
    final_shortcuts = default_shortcuts.copy()
    final_shortcuts.update(loaded_shortcuts)

    logger.debug(f"Final shortcuts loaded: {final_shortcuts}")
    return final_shortcuts

def save_shortcuts(shortcuts: Dict[str, str]) -> None:
    """Save shortcuts to config file."""
    config_dir = Path.home() / ".clipbrd"
    config_file = config_dir / "screenshot_config.json"
    temp_file = config_file.with_suffix('.tmp')
    
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
        
        # Write to temporary file first
        with open(temp_file, 'w') as f:
            json.dump({
                "shortcuts": shortcuts,
                "format": "PNG"
            }, f, indent=2)
        
        # Atomically rename
        temp_file.replace(config_file)
        logger.debug("Shortcuts saved successfully")
    except Exception as e:
        logger.error(f"Error saving shortcuts: {e}")
        if temp_file.exists():
            temp_file.unlink()
    
