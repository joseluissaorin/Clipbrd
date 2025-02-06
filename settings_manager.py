import os
import json
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk
from license_manager import LicenseManager
from glob import glob
import subprocess
import platform
from screenshot import load_shortcuts, save_shortcuts

logger = logging.getLogger(__name__)

def get_default_documents_folder() -> str:
    """Get the default documents folder with fallbacks for different systems and languages."""
    # Try standard Documents folder
    documents_folder = os.path.expanduser("~/Documents")
    if os.path.exists(documents_folder):
        return os.path.join(documents_folder, "Clipbrd")
    
    # Try Windows with OneDrive
    onedrive_docs = glob(os.path.expanduser("~\\*\\Documents"))
    if onedrive_docs:
        return os.path.join(onedrive_docs[0], "Clipbrd")
    
    # Try Spanish Windows with OneDrive
    onedrive_docs_es = glob(os.path.expanduser("~\\*\\Documentos"))
    if onedrive_docs_es:
        return os.path.join(onedrive_docs_es[0], "Clipbrd")
    
    # Try macOS
    macos_docs = os.path.expanduser("~/Library/Documents")
    if os.path.exists(macos_docs):
        return os.path.join(macos_docs, "Clipbrd")
    
    # Try Spanish language systems
    spanish_docs = os.path.expanduser("~/Documentos")
    if os.path.exists(spanish_docs):
        return os.path.join(spanish_docs, "Clipbrd")
    
    # Fallback to home directory
    return os.path.join(os.path.expanduser("~"), "Clipbrd")

def ensure_clipbrd_folder(path: str) -> str:
    """Ensure the path ends with Clipbrd and the folder exists."""
    if not path.endswith("Clipbrd"):
        path = os.path.join(path, "Clipbrd")
    
    try:
        os.makedirs(path, exist_ok=True)
    except Exception as e:
        logger.error(f"Error creating Clipbrd folder: {e}")
    
    return path

def open_folder_in_explorer(path: str):
    """Open the specified folder in the system's default file explorer."""
    try:
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":  # macOS
            subprocess.run(["open", path])
        else:  # Linux
            subprocess.run(["xdg-open", path])
    except Exception as e:
        logger.error(f"Error opening folder: {e}")
        return False
    return True

@dataclass
class AppSettings:
    """Application settings with defaults."""
    theme: str = "light"
    check_interval: float = 0.1
    debug_mode: bool = False
    shortcuts: Dict[str, str] = None
    auto_update: bool = True
    notification_sound: bool = True
    minimize_to_tray: bool = True
    startup_launch: bool = True
    max_debug_entries: int = 100
    language: str = "en"
    documents_folder: str = get_default_documents_folder()
    
    def __post_init__(self):
        if self.shortcuts is None:
            self.shortcuts = load_shortcuts()

    def save_shortcuts(self):
        """Save shortcuts to both settings and screenshot config."""
        save_shortcuts(self.shortcuts)

class SettingsManager:
    def __init__(self, app_data_dir: Optional[str] = None):
        if app_data_dir is None:
            app_data_dir = self._get_default_app_dir()
        
        self.app_data_dir = Path(app_data_dir)
        self.settings_file = self.app_data_dir / "settings.json"
        self.settings = self._load_settings()
        self.settings_window = None
        self._setup_logger()
        
    def _setup_logger(self):
        """Setup logging based on debug mode setting."""
        # Setup root logger to capture all app logs
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG if self.settings.debug_mode else logging.INFO)
        
        # Create logs directory if it doesn't exist
        log_dir = self.app_data_dir
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup file handler
        log_file = log_dir / "debug.log"
        file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        
        # Create formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        
        # Remove any existing handlers and add the new one
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        root_logger.addHandler(file_handler)
        
        # Setup console handler as well
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG if self.settings.debug_mode else logging.INFO)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        
        # Get our specific logger
        self.logger = logging.getLogger(__name__)
        self.logger.debug("Settings manager initialized with debug mode: %s", self.settings.debug_mode)

    def _update_logging_level(self):
        """Update logging level when debug mode changes."""
        new_level = logging.DEBUG if self.settings.debug_mode else logging.INFO
        self.logger.setLevel(new_level)
        self.logger.debug("Logging level updated to: %s", "DEBUG" if self.settings.debug_mode else "INFO")
        
    def _get_default_app_dir(self) -> Path:
        """Get the default application data directory."""
        if os.name == 'nt':  # Windows
            base_dir = Path(os.environ.get('APPDATA', os.path.expanduser('~')))
        else:  # macOS and Linux
            base_dir = Path(os.path.expanduser('~')) / '.config'
        
        app_dir = base_dir / 'Clipbrd'
        app_dir.mkdir(parents=True, exist_ok=True)
        return app_dir

    def _load_settings(self) -> AppSettings:
        """Load settings from file or create defaults."""
        try:
            if self.settings_file.exists():
                with open(self.settings_file, 'r') as f:
                    data = json.load(f)
                return AppSettings(**data)
        except Exception as e:
            logger.error(f"Error loading settings: {e}")
        
        return AppSettings()

    def save_settings(self) -> bool:
        """Save current settings to file."""
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(asdict(self.settings), f, indent=2)
            self._update_logging_level()  # Update logging level after settings change
            self.logger.debug("Settings saved successfully")
            return True
        except Exception as e:
            self.logger.error(f"Error saving settings: {e}")
            return False

    def update_setting(self, key: str, value: Any) -> bool:
        """Update a single setting."""
        try:
            if hasattr(self.settings, key):
                old_value = getattr(self.settings, key)
                setattr(self.settings, key, value)
                self.logger.debug(f"Setting '{key}' updated: {old_value} -> {value}")
                success = self.save_settings()
                if key == 'debug_mode':
                    self._update_logging_level()
                return success
            self.logger.warning(f"Attempted to update non-existent setting: {key}")
            return False
        except Exception as e:
            self.logger.error(f"Error updating setting {key}: {e}")
            return False

    def get_setting(self, key: str) -> Any:
        """Get a setting value."""
        value = getattr(self.settings, key, None)
        self.logger.debug(f"Retrieved setting '{key}': {value}")
        return value

    def show_dialog(self):
        """Show settings dialog with dynamic sizing."""
        # If window already exists, just focus it
        if self.settings_window is not None:
            try:
                self.settings_window.focus_force()
                return
            except tk.TclError:
                # Window was destroyed but reference remains
                self.settings_window = None

        # Create new window
        self.settings_window = tk.Tk()
        root = self.settings_window
        root.title("Clipbrd Settings")
        
        # Define on_closing function at the start
        def on_closing():
            self.settings_window = None
            root.destroy()
            
        # Set window close handler
        root.protocol("WM_DELETE_WINDOW", on_closing)
        
        # Set window icon
        icon_dir = os.path.join(os.path.dirname(__file__), 'assets', 'icons')
        icon_path = os.path.join(icon_dir, 'clipbrd_windows.ico' if os.name == 'nt' else 'clipbrd_macos.png')
        
        if os.path.exists(icon_path):
            try:
                if os.name == 'nt':  # Windows
                    root.iconbitmap(icon_path)
                else:  # macOS/Linux
                    img = Image.open(icon_path)
                    photo = ImageTk.PhotoImage(img)
                    root.iconphoto(True, photo)
                    root.tk.call('wm', 'iconphoto', root._w, photo)
            except Exception as e:
                logger.error(f"Error setting window icon: {e}")
        
        # Get screen dimensions
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        
        # Create main container
        main_container = ttk.Frame(root)
        main_container.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        
        # Configure grid weights for root
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(0, weight=1)
        
        # Create notebook for tabs
        notebook = ttk.Notebook(main_container)
        notebook.grid(row=0, column=0, sticky="nsew")
        
        # Configure grid weights for main container
        main_container.grid_columnconfigure(0, weight=1)
        main_container.grid_rowconfigure(0, weight=1)
        
        # Create frames for each tab
        general_frame = ttk.Frame(notebook)
        notebook.add(general_frame, text="General")
        
        # Configure grid weights for frames
        general_frame.grid_columnconfigure(1, weight=1)

        # Screenshot shortcut in general settings
        shortcut_frame = ttk.LabelFrame(general_frame, text="Screenshot", padding="10")
        shortcut_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        shortcut_frame.grid_columnconfigure(1, weight=1)
        
        shortcut_label = ttk.Label(shortcut_frame, text="Full Screen Shortcut:")
        shortcut_entry = ttk.Entry(shortcut_frame, width=20)
        shortcut_entry.insert(0, self.settings.shortcuts.get("full_screenshot", "<ctrl>+<shift>+f"))
        
        shortcut_label.grid(row=0, column=0, padx=(0,5), pady=5, sticky='w')
        shortcut_entry.grid(row=0, column=1, padx=5, pady=5, sticky='w')
        
        # License Frame
        license_frame = ttk.LabelFrame(general_frame, text="License", padding="10")
        license_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 20))

        # License Status
        license_manager = LicenseManager()

        def refresh_license_frame():
            # Clear all widgets in license frame
            for widget in license_frame.winfo_children():
                widget.destroy()

            def check_license():
                # Get stored license info
                license_key, license_data = license_manager.get_stored_license()
                
                if license_key and license_data:
                    result = license_manager.verify_license()
                    if result['status'] == 'success':
                        # Show active license status
                        ttk.Label(license_frame, text=result['message']).grid(row=0, column=0, sticky=tk.W)
                        ttk.Button(license_frame, text="Deactivate License", 
                                command=handle_deactivation).grid(row=1, column=0, pady=10)
                    else:
                        show_activation_form()
                else:
                    show_activation_form()

            def show_activation_form():
                ttk.Label(license_frame, text="Enter License Key:").grid(row=0, column=0, sticky=tk.W)
                license_entry = ttk.Entry(license_frame, width=40)
                license_entry.grid(row=1, column=0, pady=5)
                
                def handle_activation():
                    key = license_entry.get().strip()
                    if not key:
                        messagebox.showerror("Error", "Please enter a license key")
                        return

                    try:
                        activate_button.configure(state="disabled", text="Activating...")
                        root.update()

                        result = license_manager.activate_license(key)
                        
                        if result['status'] == 'success':
                            messagebox.showinfo("Success", result['message'])
                            refresh_license_frame()
                        else:
                            messagebox.showerror("Error", result.get('message', 'Invalid license key'))
                            if activate_button.winfo_exists():
                                activate_button.configure(state="normal", text="Activate License")
                    except Exception as e:
                        messagebox.showerror("Error", str(e))
                        if activate_button.winfo_exists():
                            activate_button.configure(state="normal", text="Activate License")
                    finally:
                        if root.winfo_exists():
                            root.update()

                activate_button = ttk.Button(license_frame, text="Activate License", command=handle_activation)
                activate_button.grid(row=2, column=0, pady=5)

            def handle_deactivation():
                if messagebox.askyesno("Confirm Deactivation", "Are you sure you want to deactivate your license?"):
                    license_manager.clear_stored_license()
                    messagebox.showinfo("Success", "License deactivated successfully")
                    refresh_license_frame()

            # Start the license check
            check_license()

        # Initial license frame setup
        refresh_license_frame()

        # Settings Frame
        settings_frame = ttk.LabelFrame(general_frame, text="Settings", padding="10")
        settings_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
        settings_frame.grid_columnconfigure(0, weight=1)

        # Debug Mode and Log Viewer
        debug_frame = ttk.Frame(settings_frame)
        debug_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        def on_debug_toggle():
            debug_log.grid_remove() if not debug_var.get() else debug_log.grid()
            if debug_var.get():
                update_debug_log()
                # Adjust window size when showing debug log
                root.after(100, lambda: root.geometry(f"{window_width}x{window_height}"))
        
        debug_var = tk.BooleanVar(value=self.settings.debug_mode)
        debug_cb = ttk.Checkbutton(debug_frame, text="Debug Mode", variable=debug_var, command=on_debug_toggle)
        debug_cb.grid(row=0, column=0, sticky=tk.W)
        
        # Debug Log Viewer
        debug_log = ttk.Frame(settings_frame)
        debug_log.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        debug_log.grid_columnconfigure(0, weight=1)
        
        if not debug_var.get():
            debug_log.grid_remove()
            
        # Create Text widget with scrollbar for debug messages
        debug_text = tk.Text(debug_log, height=10, width=40, wrap=tk.WORD)
        debug_scrollbar = ttk.Scrollbar(debug_log, orient="vertical", command=debug_text.yview)
        debug_text.configure(yscrollcommand=debug_scrollbar.set)
        
        debug_text.grid(row=0, column=0, sticky=(tk.W, tk.E))
        debug_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # Add clear and refresh buttons
        button_frame = ttk.Frame(debug_log)
        button_frame.grid(row=1, column=0, columnspan=2, pady=5)
        
        def clear_debug_log():
            debug_text.delete(1.0, tk.END)
            
        def update_debug_log():
            if not debug_var.get():
                return
            try:
                # Get the log file path
                log_file = self.app_data_dir / "debug.log"
                if log_file.exists():
                    with open(log_file, 'r', encoding='utf-8') as f:
                        # Read last 50 lines
                        lines = f.readlines()[-50:]
                        debug_text.delete(1.0, tk.END)
                        debug_text.insert(tk.END, "".join(lines))
                        debug_text.see(tk.END)  # Scroll to bottom
            except Exception as e:
                debug_text.delete(1.0, tk.END)
                debug_text.insert(tk.END, f"Error reading debug log: {str(e)}")
        
        ttk.Button(button_frame, text="Clear", command=clear_debug_log).grid(row=0, column=0, padx=5)
        ttk.Button(button_frame, text="Refresh", command=update_debug_log).grid(row=0, column=1, padx=5)
        
        # Auto-update debug log every 2 seconds if debug mode is on
        def auto_update_debug():
            if root.winfo_exists() and debug_var.get():
                update_debug_log()
                root.after(2000, auto_update_debug)
        
        auto_update_debug()

        # Other settings continue below the debug section
        # Notification Sound
        notif_sound_var = tk.BooleanVar(value=self.settings.notification_sound)
        ttk.Checkbutton(settings_frame, text="Notification Sound", variable=notif_sound_var).grid(row=2, column=0, sticky=tk.W, pady=5)

        # Minimize to Tray
        minimize_var = tk.BooleanVar(value=self.settings.minimize_to_tray)
        ttk.Checkbutton(settings_frame, text="Minimize to Tray", variable=minimize_var).grid(row=3, column=0, sticky=tk.W, pady=5)

        # # Language
        # ttk.Label(settings_frame, text="Language:").grid(row=4, column=0, sticky=tk.W, pady=5)
        # lang_var = tk.StringVar(value=self.settings.language)
        # lang_combo = ttk.Combobox(settings_frame, textvariable=lang_var, values=["en", "es", "fr", "de"], state="readonly")
        # lang_combo.grid(row=4, column=1, sticky=tk.W, pady=5)

        # Document Folder Selection
        folder_frame = ttk.Frame(settings_frame)
        folder_frame.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        folder_frame.grid_columnconfigure(1, weight=1)
        
        ttk.Label(folder_frame, text="Documents Folder:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        folder_var = tk.StringVar(value=self.settings.documents_folder)
        folder_entry = ttk.Entry(folder_frame, textvariable=folder_var, state="readonly")
        folder_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5)
        
        def browse_folder():
            folder = filedialog.askdirectory(initialdir=folder_var.get())
            if folder:
                folder = ensure_clipbrd_folder(folder)
                folder_var.set(folder)
        
        button_frame = ttk.Frame(folder_frame)
        button_frame.grid(row=0, column=2)
        
        ttk.Button(button_frame, text="Browse", command=browse_folder).grid(row=0, column=0, padx=2)
        
        def open_current_folder():
            current_folder = folder_var.get()
            if not os.path.exists(current_folder):
                try:
                    os.makedirs(current_folder, exist_ok=True)
                except Exception as e:
                    messagebox.showerror("Error", f"Could not create folder: {e}")
                    return
            if not open_folder_in_explorer(current_folder):
                messagebox.showerror("Error", "Could not open the folder.")
        
        ttk.Button(button_frame, text="Open", command=open_current_folder).grid(row=0, column=1, padx=2)

        def save_settings():
            try:
                self.settings.debug_mode = debug_var.get()
                self.settings.notification_sound = notif_sound_var.get()
                self.settings.minimize_to_tray = minimize_var.get()
                self.settings.language = lang_var.get()
                self.settings.documents_folder = folder_var.get()
                
                # Save screenshot shortcut
                new_shortcuts = {"full_screenshot": shortcut_entry.get()}
                self.settings.shortcuts = new_shortcuts
                save_shortcuts(new_shortcuts)
                
                self.save_settings()
                messagebox.showinfo("Success", "Settings saved successfully!")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save settings: {e}")
            finally:
                on_closing()

        # Save Button
        ttk.Button(general_frame, text="Save", command=save_settings).grid(row=3, column=0, pady=20)

        try:
            root.mainloop()
        except Exception as e:
            logger.error(f"Error in settings dialog: {e}")
            self.settings_window = None
            try:
                root.destroy()
            except:
                pass