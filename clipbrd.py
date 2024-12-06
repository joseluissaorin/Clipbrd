# clipbrd.py
import os
import sys
import asyncio
import logging
from typing import Dict, Callable, Optional

from platform_interface import PlatformConfig, create_platform_interface
from settings_manager import SettingsManager
from dependency_manager import DependencyManager
from clipboard_processing import ClipboardProcessor
from progress_indicator import ProgressIndicator

class Clipbrd:
    def __init__(self):
        self.settings = SettingsManager()
        self.clipboard = ClipboardProcessor()
        self.platform = None
        self.running = False
        self.progress = ProgressIndicator(app=self)
        self.setup_logging()
    
    def setup_logging(self):
        logging.basicConfig(
            level=logging.DEBUG if self.settings.get_setting('debug_mode') else logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger('Clipbrd')
    
    async def initialize(self):
        """Initialize the application."""
        try:
            # Initialize dependencies
            dep_manager = DependencyManager()
            if not await dep_manager.install_dependencies():
                self.logger.error("Failed to install dependencies")
                return False
            
            # Setup platform interface
            platform_config = PlatformConfig(
                app_name="Clipbrd",
                icon_path=self.get_icon_path(),
                menu_items=self.get_menu_items(),
                debug_mode=self.settings.get_setting('debug_mode')
            )
            self.platform = create_platform_interface(platform_config)
            
            if not self.platform.initialize():
                self.logger.error("Failed to initialize platform interface")
                return False
            
            # Initialize clipboard processor
            await self.clipboard.initialize()
            
            self.running = True
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize application: {e}")
            return False
    
    def get_icon_path(self) -> str:
        """Get the appropriate icon path based on the platform."""
        icon_dir = os.path.join(os.path.dirname(__file__), 'assets', 'icons')
        if sys.platform == 'darwin':
            return os.path.join(icon_dir, 'clipbrd_macos.png')
        else:
            return os.path.join(icon_dir, 'clipbrd_windows.ico')
    
    def get_menu_items(self) -> Dict[str, Callable]:
        """Get the menu items configuration."""
        return {
            'Settings': self.show_settings,
            'About': self.show_about,
            'Quit': self.quit
        }
    
    def show_settings(self, _=None):
        """Show settings dialog."""
        self.settings.show_dialog()
    
    def show_about(self, _=None):
        """Show about dialog."""
        self.platform.show_notification(
            "About Clipbrd",
            "Clipbrd - Your AI-powered clipboard assistant\nVersion 1.0.0"
        )
    
    def quit(self, _=None):
        """Quit the application."""
        self.running = False
        self.cleanup()
        sys.exit(0)
    
    async def process_clipboard(self):
        """Process clipboard content."""
        try:
            while self.running:
                content = await self.clipboard.get_content()
                if content:
                    self.progress.start("Processing clipboard content...")
                    result = await self.clipboard.process_content(content)
                    self.progress.stop()
                    
                    if result:
                        self.platform.update_icon("✓")
                        self.platform.show_notification(
                            "Content Processed",
                            "Clipboard content has been processed successfully"
                        )
                    else:
                        self.platform.update_icon("!")
                
                await asyncio.sleep(1)
        except Exception as e:
            self.logger.error(f"Error processing clipboard: {e}")
            self.platform.update_icon("⚠")
    
    def cleanup(self):
        """Clean up resources."""
        try:
            if self.platform:
                self.platform.cleanup()
            self.clipboard.cleanup()
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
    
    async def run(self):
        """Run the application."""
        if await self.initialize():
            try:
                clipboard_task = asyncio.create_task(self.process_clipboard())
                self.platform.run()  # This blocks until the app is quit
                await clipboard_task  # Ensure clipboard task is properly cleaned up
            except Exception as e:
                self.logger.error(f"Error running application: {e}")
            finally:
                self.cleanup()
        else:
            self.logger.error("Failed to initialize application")

def main():
    """Main entry point."""
    app = Clipbrd()
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(app.run())

if __name__ == '__main__':
    main()