# clipbrd.py
import os
import sys
import asyncio
import logging
from typing import Dict, Callable, Optional

from platform_interface import PlatformConfig, create_platform_interface, IconState
from settings_manager import SettingsManager
from dependency_manager import DependencyManager
from clipboard_processing import ClipboardProcessor
from license_manager import LicenseManager
from llmrouter import LLMRouter
from document_processing import process_documents
from screenshot import ScreenshotManager, ScreenshotConfig, ScreenshotType
from pynput import keyboard

def is_running_from_exe() -> bool:
    """Check if the application is running from a compiled executable."""
    return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')

def load_environment_variables():
    """Load environment variables based on execution context."""
    if not is_running_from_exe():
        try:
            from dotenv import load_dotenv
            load_dotenv()
            logging.info("Loaded environment variables from .env file")
        except ImportError:
            logging.warning("python-dotenv not installed, skipping .env file")
    else:
        logging.info("Running from executable, using hardcoded environment variables")

# Load environment variables at startup
load_environment_variables()

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
        self.reset_hotkey_listener = None
    
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
            
            # Setup platform interface, passing settings
            platform_config = PlatformConfig(
                app_name="Clipbrd",
                icon_path=self.get_icon_path(),
                menu_items=self.get_menu_items(),
                debug_mode=self.settings.get_setting('debug_mode')
            )
            self.platform = create_platform_interface(platform_config, self.settings)
            
            if not self.platform.initialize():
                self.logger.error("Failed to initialize platform interface")
                return False

            # Set up screenshot callback
            self._setup_screenshot_shortcuts()

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
            docs_folder = self.settings.get_setting('documents_folder')
            if not os.path.exists(docs_folder):
                os.makedirs(docs_folder, exist_ok=True)
            
            # Exclude processed_files directory from document processing
            exclude_patterns = ['processed_files/*', '**/processed_files/*']
            
            try:
                documents, inverted_index, stats = await process_documents(docs_folder, exclude_patterns=exclude_patterns)
                
                # Initialize document processing components
                if documents and len(documents) > 0:
                    self.documents = documents
                    self.inverted_index = inverted_index
                    # Ensure inverted_index is properly initialized before getting search function
                    if self.inverted_index and hasattr(self.inverted_index, 'search'):
                        self.search = self.inverted_index.search
                        self.logger.info("Search function successfully initialized")
                    else:
                        self.logger.error("Invalid inverted index or missing search function")
                        self.search = None
                        self.inverted_index = None
                    self.logger.info(f"Successfully loaded {len(documents)} documents")
                    self.logger.info(f"Document processing stats: {stats}")
                    self.logger.debug(f"Search function type: {type(self.search) if self.search else 'None'}")
                    self.logger.debug(f"Inverted index type: {type(self.inverted_index) if self.inverted_index else 'None'}")
                else:
                    self.logger.warning("No documents found in the specified folder")
                    # Initialize empty components
                    self.documents = []
                    self.inverted_index = None
                    self.search = None
            except Exception as e:
                self.logger.error(f"Error processing documents: {e}")
                # Initialize empty components
                self.documents = []
                self.inverted_index = None
                self.search = None
            
            # Initialize clipboard processor with search components
            self.clipboard = ClipboardProcessor()
            
            # Pass the search components to the clipboard processor
            if self.search and self.inverted_index and self.documents:
                self.logger.info("Passing initialized search components to clipboard processor")
                self.clipboard.search = self.search
                self.clipboard.inverted_index = self.inverted_index
                self.clipboard.documents = self.documents
            else:
                self.logger.warning("Search components not available - clipboard processor will run without context")
                self.clipboard.search = None
                self.clipboard.inverted_index = None
                self.clipboard.documents = self.documents if self.documents else []

            # Setup the reset icon shortcut listener
            self._setup_reset_shortcut()

            self.running = True
            self.logger.info("Application initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize application: {e}", exc_info=True)
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
            # Stop the reset shortcut listener
            if self.reset_hotkey_listener:
                self.logger.debug("Stopping reset hotkey listener")
                self.reset_hotkey_listener.stop()
                self.reset_hotkey_listener = None

            if self.platform:
                self.platform.cleanup()
            if self.clipboard:
                self.clipboard.cleanup()
            # Cleanup screenshot manager shortcuts
            if hasattr(self, 'screenshot_manager') and self.screenshot_manager:
                self.screenshot_manager.cleanup()
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
            # Pass the main loop to platform interface
            self.platform.main_loop = self.main_loop
            
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
            # Signal that platform is ready to start
            asyncio.run_coroutine_threadsafe(
                self._set_ready(ready_event),
                self.main_loop
            )
            
            # Run the platform interface (blocking call)
            self.platform.run()
        except Exception as e:
            self.logger.error(f"Error in platform interface: {e}")
            self.running = False

    def _setup_screenshot_shortcuts(self):
        """Set up screenshot keyboard shortcuts."""
        # Get shortcuts from settings
        shortcuts = self.settings.get_setting('shortcuts')
        
        # Create screenshot config
        config = ScreenshotConfig(shortcuts=shortcuts)
        
        # Initialize screenshot manager
        self.screenshot_manager = ScreenshotManager(config)
        
        # Set up callback for screenshot actions
        def screenshot_callback(screenshot_type: ScreenshotType):
            # Schedule the async handler in the event loop
            asyncio.run_coroutine_threadsafe(
                self.handle_screenshot(screenshot_type.name.lower()),
                self.main_loop
            )
        
        self.screenshot_manager.set_callback(screenshot_callback)
        
        # Initialize the manager (now synchronous)
        if self.screenshot_manager.initialize():
            self.logger.debug("Screenshot manager initialized with shortcuts")
        else:
            self.logger.error("Failed to initialize screenshot manager")

    def _setup_reset_shortcut(self):
        """Set up the keyboard shortcut to reset the icon to IDLE."""
        try:
            shortcuts = self.settings.get_setting('shortcuts')
            if not shortcuts:
                self.logger.warning("Shortcuts not loaded, cannot set up reset shortcut.")
                return

            shortcut_key = shortcuts.get('reset_icon_shortcut', '<ctrl>+<shift>+i')

            if not shortcut_key:
                 self.logger.warning("Reset icon shortcut key is empty.")
                 return

            def on_reset_activate():
                self.logger.info(f"Reset icon shortcut ({shortcut_key}) activated.")
                self.update_icon(IconState.IDLE)

            if self.reset_hotkey_listener:
                self.reset_hotkey_listener.stop()

            self.reset_hotkey_listener = keyboard.GlobalHotKeys({
                shortcut_key: on_reset_activate
            })
            self.reset_hotkey_listener.start()
            self.logger.info(f"Reset icon shortcut '{shortcut_key}' set up successfully.")

        except Exception as e:
            self.logger.error(f"Error setting up reset icon shortcut: {e}", exc_info=True)
            if self.reset_hotkey_listener:
                 try: self.reset_hotkey_listener.stop()
                 except: pass
            self.reset_hotkey_listener = None

    async def handle_screenshot(self, screenshot_type: str):
        """Handle screenshot capture request."""
        try:
            if not self.clipboard:
                self.logger.error("Screenshot failed: Clipboard processor not initialized")
                raise Exception("Clipboard processor not initialized")

            self.logger.info(f"Starting screenshot capture: type={screenshot_type}")
            self.update_icon(IconState.SCREENSHOT)
            
            # Take screenshot using screenshot manager (now synchronous)
            self.logger.debug("Invoking screenshot manager")
            screenshot_data = self.screenshot_manager.take_screenshot(
                getattr(ScreenshotType, screenshot_type.upper())
            )
            
            if screenshot_data:
                self.logger.info("Screenshot captured successfully")
                self.logger.debug("Storing screenshot in clipboard processor")
                # Store screenshot in clipboard processor
                self.clipboard.set_screenshot(screenshot_data)
                
                self.logger.info("Starting screenshot processing")
                # Process screenshot (this will handle its own state management)
                await self.clipboard.process_screenshot(self)
                self.logger.info("Screenshot processing completed")
            else:
                self.logger.error("Screenshot capture failed: No data returned")
                raise Exception("Failed to capture screenshot")
                
        except Exception as e:
            self.logger.error(f"Screenshot error: {e}", exc_info=True)
            self.update_icon(IconState.ERROR)
            if self.platform:
                self.platform.show_notification(
                    "Screenshot Error",
                    f"Failed to take screenshot: {str(e)}"
                )
            await asyncio.sleep(2)
            self.update_icon(IconState.IDLE)
            self.logger.info("Screenshot operation completed with errors")

def main():
    """Main entry point."""
    app = Clipbrd()
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(app.run())

if __name__ == '__main__':
    main()