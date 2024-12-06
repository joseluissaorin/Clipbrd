# clipbrd.py
import os
import sys
import asyncio
import logging
from typing import Dict, Callable, Optional
from dotenv import load_dotenv

from platform_interface import PlatformConfig, create_platform_interface
from settings_manager import SettingsManager
from dependency_manager import DependencyManager
from clipboard_processing import ClipboardProcessor
from license_manager import LicenseManager
from llmrouter import LLMRouter
from document_processing import process_documents

# Load environment variables
load_dotenv()

class MockClipboardProcessor:
    """A mock clipboard processor that does nothing but allows the app to run."""
    def __init__(self):
        self.logger = logging.getLogger('MockClipboard')
        self.logger.info("Mock clipboard processor initialized")

    async def process_clipboard(self, app) -> None:
        """Mock processing that does nothing."""
        await asyncio.sleep(1)
        return None

    def cleanup(self):
        """Mock cleanup."""
        pass

    async def process_screenshot(self, app) -> None:
        """Mock screenshot processing."""
        await asyncio.sleep(1)
        return None

class Clipbrd:
    # Class constants
    DEFAULT_POLLING_INTERVAL = 1  # Default polling interval in seconds

    def __init__(self):
        self.settings = SettingsManager()
        self.platform = None
        self.running = False
        self.debug_info = []
        self.setup_logging()
        # Initialize required attributes
        self.llm_router = None
        self.search = None
        self.inverted_index = None
        self.documents = None
        # Initialize clipboard processor after license check
        self.clipboard = None
    
    def setup_logging(self):
        logging.basicConfig(
            level=logging.DEBUG if self.settings.get_setting('debug_mode') else logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger('Clipbrd')
    
    def update_icon(self, icon_state, text: Optional[str] = None):
        """Update the system tray icon state."""
        if self.platform:
            self.platform.update_icon(icon_state, text)
    
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

            # Check license before initializing components
            license_manager = LicenseManager()
            if not license_manager.is_license_valid():
                self.logger.warning("No valid license found - running in limited mode")
                self.clipboard = MockClipboardProcessor()
                self.running = True
                return True

            # Initialize LLM Router with API keys from environment
            self.llm_router = LLMRouter(
                anthropic_api_key=os.getenv('ANTHROPIC_API_KEY'),
                openai_api_key=os.getenv('OPENAI_API_KEY'),
                deepinfra_api_key=os.getenv('DEEPINFRA_API_KEY'),
                gemini_api_key=os.getenv('GOOGLEAI_API_KEY'),
            )

            # Initialize document processing components
            docs_folder = os.path.join(os.path.dirname(__file__), 'docs')
            self.documents, self.inverted_index, stats = await process_documents(docs_folder)
            self.search = self.inverted_index.search  # Use the search method directly
            
            # Initialize clipboard processor
            self.clipboard = ClipboardProcessor()
            
            self.running = True
            self.logger.info("Application initialized successfully")
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
                try:
                    await self.clipboard.process_clipboard(self)
                    await asyncio.sleep(self.DEFAULT_POLLING_INTERVAL)
                except Exception as e:
                    self.logger.error(f"Error in clipboard processing loop: {e}")
                    await asyncio.sleep(1)  # Wait before retrying
                    
        except Exception as e:
            self.logger.error(f"Error in clipboard monitoring: {e}")
            self.update_icon("⚠")
    
    def cleanup(self):
        """Clean up resources."""
        try:
            if self.platform:
                self.platform.cleanup()
            if self.clipboard:
                self.clipboard.cleanup()
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
    
    async def run(self):
        """Run the application."""
        if not await self.initialize():
            self.logger.error("Failed to initialize application")
            return

        try:
            # Create an event to signal when the platform interface is ready
            platform_ready = asyncio.Event()
            
            # Store the main event loop for cross-thread communication
            self.main_loop = asyncio.get_running_loop()
            
            # Run platform interface in a separate thread
            import threading
            platform_thread = threading.Thread(
                target=self._run_platform_interface,
                args=(platform_ready,),
                daemon=True
            )
            platform_thread.start()

            # Wait for platform interface to be ready
            await platform_ready.wait()

            # Run clipboard monitoring in the main asyncio event loop
            while self.running:
                try:
                    await self.process_clipboard()
                except Exception as e:
                    self.logger.error(f"Error in main loop: {e}")
                    await asyncio.sleep(1)

        except Exception as e:
            self.logger.error(f"Error running application: {e}")
        finally:
            self.cleanup()

    async def _set_ready(self, ready_event):
        """Coroutine to set the ready event."""
        ready_event.set()

    def _run_platform_interface(self, ready_event):
        """Run the platform interface in a separate thread."""
        try:
            # Signal that platform is ready to start using the stored main loop
            asyncio.run_coroutine_threadsafe(
                self._set_ready(ready_event),
                self.main_loop
            )
            
            # Run the platform interface (blocking call)
            self.platform.run()
        except Exception as e:
            self.logger.error(f"Error in platform interface: {e}")
            self.running = False

def main():
    """Main entry point."""
    app = Clipbrd()
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(app.run())

if __name__ == '__main__':
    main()