import os
import sys
import subprocess
import json
import tempfile
import shutil
import tkinter as tk
from tkinter import messagebox
from pathlib import Path
from typing import Dict, List, Optional
import logging
import webbrowser

class DependencyManager:
    LIBREOFFICE_URL = "https://www.libreoffice.org/download/download/"

    def __init__(self):
        self.app_data_dir = self._get_app_data_dir()
        self.temp_dir = tempfile.mkdtemp(prefix="clipbrd_")
        self.dependencies_file = os.path.join(self.app_data_dir, "dependencies.json")
        self.logger = self._setup_logger()
        
    def _setup_logger(self) -> logging.Logger:
        logger = logging.getLogger("DependencyManager")
        logger.setLevel(logging.INFO)
        return logger

    def _get_app_data_dir(self) -> str:
        """Get the appropriate application data directory based on the platform."""
        if sys.platform == "win32":
            base_dir = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        elif sys.platform == "darwin":
            base_dir = os.path.expanduser("~/Library/Application Support")
        else:
            base_dir = os.path.expanduser("~/.local/share")
        
        app_dir = os.path.join(base_dir, "Clipbrd")
        os.makedirs(app_dir, exist_ok=True)
        return app_dir

    def _show_libreoffice_install_dialog(self) -> bool:
        """Show a dialog prompting user to install LibreOffice."""
        root = tk.Tk()
        root.withdraw()  # Hide the main window
        
        message = (
            "LibreOffice is required but not installed.\n\n"
            "Would you like to open the LibreOffice download page?\n\n"
            "After installation, please:\n"
            "1. Complete the LibreOffice installation\n"
            "2. Restart your computer\n"
            "3. Start Clipbrd again"
        )
        
        try:
            if messagebox.askyesno("LibreOffice Required", message):
                # Ensure the URL opens in a new browser window
                webbrowser.open(self.LIBREOFFICE_URL)
                root.after(1000, root.destroy)  # Destroy the root window after 1 second
                root.mainloop()
                return True
            else:
                root.destroy()
                return False
        except Exception as e:
            self.logger.error(f"Error showing LibreOffice installation dialog: {e}")
            root.destroy()
            return False

    def _check_libreoffice_installation(self) -> bool:
        """Check if LibreOffice is installed and in PATH."""
        try:
            if sys.platform == "win32":
                # Check common installation paths on Windows
                program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
                program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
                
                possible_paths = [
                    os.path.join(program_files, "LibreOffice", "program"),
                    os.path.join(program_files_x86, "LibreOffice", "program")
                ]
                
                # Check if soffice.exe exists in any of these paths
                for path in possible_paths:
                    if os.path.exists(os.path.join(path, "soffice.exe")):
                        # Add to PATH if not already there
                        if path not in os.environ["PATH"]:
                            os.environ["PATH"] = path + os.pathsep + os.environ["PATH"]
                        return True
                
                # If LibreOffice is not found, show installation dialog
                self._show_libreoffice_install_dialog()
                return False
            else:
                # On Unix-like systems, check if soffice is in PATH
                result = subprocess.run(["which", "soffice"], capture_output=True)
                if result.returncode != 0:
                    self._show_libreoffice_install_dialog()
                    return False
                return True
        except Exception as e:
            self.logger.error(f"Error checking LibreOffice installation: {e}")
            self._show_libreoffice_install_dialog()
            return False

    def _get_required_dependencies(self) -> Dict[str, str]:
        """Return the minimum required dependencies with their versions."""
        return {
            "pillow": "10.0.0",
            "pynput": "1.7.6",
            "python-dotenv": "1.0.0",
            "keyring": "24.2.0",
            "fairy-doc": "0.1.0"
        }

    async def verify_dependencies(self) -> bool:
        """Verify that all required dependencies are installed and at correct versions."""
        try:
            # First check LibreOffice
            if not self._check_libreoffice_installation():
                self.logger.error("LibreOffice is not installed or not in PATH")
                return False

            # Then check Python packages
            import pkg_resources
            required = self._get_required_dependencies()
            
            for package, version in required.items():
                try:
                    pkg_resources.require(f"{package}>={version}")
                except (pkg_resources.VersionConflict, pkg_resources.DistributionNotFound):
                    return False
            return True
        except Exception as e:
            self.logger.error(f"Error verifying dependencies: {e}")
            return False

    async def install_dependencies(self) -> bool:
        """Install or update required dependencies."""
        try:
            # Check LibreOffice first
            if not self._check_libreoffice_installation():
                self.logger.error("LibreOffice is required but not installed. Please install LibreOffice and add it to PATH.")
                return False

            if getattr(sys, 'frozen', False):
                # Skip Python package installation if running as compiled binary
                return True

            # required = self._get_required_dependencies()
            # pip_cmd = [sys.executable, "-m", "pip", "install"]
            
            # # Install fairy-doc from GitHub
            # try:
            #     subprocess.run([*pip_cmd, "git+https://github.com/opendatalab/magic-doc.git"], 
            #                  check=True, 
            #                  capture_output=True)
            # except subprocess.CalledProcessError as e:
            #     self.logger.error(f"Failed to install fairy-doc from GitHub: {e}")
            #     return False

            # # Install other dependencies
            # for package, version in required.items():
            #     if package != "fairy-doc":  # Skip fairy-doc as it's already installed
            #         try:
            #             subprocess.run([*pip_cmd, f"{package}>={version}"], 
            #                          check=True, 
            #                          capture_output=True)
            #         except subprocess.CalledProcessError as e:
            #             self.logger.error(f"Failed to install {package}: {e}")
            #             return False
            
            return True
        except Exception as e:
            self.logger.error(f"Error installing dependencies: {e}")
            return False

    def cleanup(self):
        """Clean up temporary files and directories."""
        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")

    def get_binary_info(self) -> Dict[str, str]:
        """Get information about the current binary."""
        return {
            "version": "1.0.0",
            "platform": sys.platform,
            "python_version": sys.version,
            "frozen": getattr(sys, 'frozen', False),
            "executable": sys.executable
        }

    def check_for_updates(self) -> Optional[str]:
        """Check if there's a new version available."""
        # TODO: Implement version checking against a remote endpoint
        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup() 