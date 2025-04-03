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
from screenshot import load_shortcuts, save_shortcuts, ScreenshotType

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
    theme: str = "dark"
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
    formula_screenshot_pipeline: bool = False

    def __post_init__(self):
        if self.shortcuts is None:
            self.shortcuts = load_shortcuts()

    def save_shortcuts(self):
        """Save shortcuts to both settings and screenshot config."""
        default_shortcuts = {
            "full_screenshot": "<ctrl>+<shift>+f",
            "reset_icon_shortcut": "<ctrl>+<shift>+i"
        }
        for key, value in default_shortcuts.items():
            if key not in self.shortcuts:
                self.shortcuts[key] = value
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
                # Make sure loaded data includes new fields, providing defaults if missing
                loaded_settings = AppSettings(**data)
                # Ensure shortcuts are loaded correctly, merging with defaults
                loaded_settings.shortcuts = load_shortcuts() # Reload shortcuts to merge saved ones with defaults
                if 'formula_screenshot_pipeline' not in data:
                    loaded_settings.formula_screenshot_pipeline = False # Default if missing
                if 'theme' not in data:
                    loaded_settings.theme = 'dark' # Default if missing
                return loaded_settings
        except Exception as e:
            logger.error(f"Error loading settings: {e}, falling back to defaults.")

        # Fallback to default AppSettings if loading fails or file doesn't exist
        default_settings = AppSettings()
        default_settings.shortcuts = load_shortcuts() # Ensure defaults have shortcuts loaded
        return default_settings

    def save_settings(self) -> bool:
        """Save current settings to file."""
        try:
            # Ensure shortcuts are saved separately via its dedicated mechanism if needed elsewhere
            # The AppSettings dataclass will handle serializing the current state of self.settings.shortcuts
            with open(self.settings_file, 'w') as f:
                json.dump(asdict(self.settings), f, indent=2)
            self._update_logging_level()  # Update logging level after settings change
            self.logger.debug("Settings saved successfully to settings.json")
            return True
        except Exception as e:
            self.logger.error(f"Error saving settings to settings.json: {e}")
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
        """Show settings dialog with dynamic sizing and layout."""
        # If window already exists, just focus it
        if self.settings_window is not None:
            try:
                self.settings_window.focus_force()
                self.settings_window.lift()  # Raise window to top
                if os.name == 'nt': # On Windows, this helps with focus issues
                    self.settings_window.attributes('-topmost', 1)
                    self.settings_window.after(100, lambda: self.settings_window.attributes('-topmost', 0))
                return
            except tk.TclError:
                self.settings_window = None # Window was destroyed

        # Create new window
        self.settings_window = tk.Tk()
        root = self.settings_window
        root.title("Clipbrd Settings")

        # Ensure window appears in the foreground
        root.lift()
        root.focus_force()
        if os.name == 'nt':
            try:
                root.attributes('-topmost', 1)
                root.after(100, lambda: root.attributes('-topmost', 0))
            except Exception as e:
                self.logger.error(f"Error setting topmost attribute: {e}")

        # Define on_closing function
        def on_closing():
            self.settings_window = None
            root.destroy()

        root.protocol("WM_DELETE_WINDOW", on_closing)

        # Set window icon
        icon_dir = os.path.join(os.path.dirname(__file__), 'assets', 'icons')
        icon_path = os.path.join(icon_dir, 'clipbrd_windows.ico' if os.name == 'nt' else 'clipbrd_macos.png')
        if os.path.exists(icon_path):
            try:
                if os.name == 'nt':
                    root.iconbitmap(icon_path)
                else:
                    img = Image.open(icon_path)
                    photo = ImageTk.PhotoImage(img)
                    root.iconphoto(True, photo)
            except Exception as e:
                logger.error(f"Error setting window icon: {e}")

        # Create main container & configure root grid
        main_container = ttk.Frame(root, padding="10")
        main_container.grid(row=0, column=0, sticky="nsew")
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(0, weight=1)

        # Configure main container grid
        main_container.grid_columnconfigure(0, weight=1)
        main_container.grid_rowconfigure(0, weight=1)

        # Create notebook
        notebook = ttk.Notebook(main_container)
        notebook.grid(row=0, column=0, sticky="nsew")

        # === General Tab ===
        general_frame = ttk.Frame(notebook, padding="10")
        notebook.add(general_frame, text="General")
        general_frame.grid_columnconfigure(0, weight=1)
        general_frame.grid_rowconfigure(3, weight=1) # Allow Debug log row to expand

        # --- Row Management for General Tab ---
        general_row = 0

        # --- License Frame ---
        license_frame = ttk.LabelFrame(general_frame, text="License", padding="10")
        license_frame.grid(row=general_row, column=0, sticky="ew", pady=(0, 10))
        license_frame.grid_columnconfigure(0, weight=1)
        general_row += 1

        license_manager = LicenseManager()

        def refresh_license_frame():
            for widget in license_frame.winfo_children():
                widget.destroy()

            def check_license():
                license_key, license_data = license_manager.get_stored_license()
                if license_key and license_data:
                    result = license_manager.verify_license()
                    if result['status'] == 'success':
                        ttk.Label(license_frame, text=result['message']).grid(row=0, column=0, sticky=tk.W)
                        ttk.Button(license_frame, text="Deactivate License", command=handle_deactivation).grid(row=1, column=0, pady=5, sticky=tk.W)
                    else:
                        show_activation_form()
                else:
                    show_activation_form()

            def show_activation_form():
                ttk.Label(license_frame, text="Enter License Key:").grid(row=0, column=0, sticky=tk.W)
                license_entry = ttk.Entry(license_frame, width=40)
                license_entry.grid(row=1, column=0, pady=(5,0), sticky=tk.W)
                activate_button = ttk.Button(license_frame, text="Activate License", command=lambda: handle_activation(license_entry, activate_button))
                activate_button.grid(row=2, column=0, pady=5, sticky=tk.W)

            def handle_activation(license_entry, activate_button):
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
                        if activate_button.winfo_exists(): activate_button.configure(state="normal", text="Activate License")
                except Exception as e:
                    messagebox.showerror("Error", str(e))
                    if activate_button.winfo_exists(): activate_button.configure(state="normal", text="Activate License")
                finally:
                    if root.winfo_exists(): root.update()

            def handle_deactivation():
                if messagebox.askyesno("Confirm Deactivation", "Are you sure you want to deactivate your license?"):
                    license_manager.clear_stored_license()
                    messagebox.showinfo("Success", "License deactivated successfully")
                    refresh_license_frame()

            check_license()

        refresh_license_frame() # Initial license check

        # --- Settings Frame ---
        settings_row = 0
        app_settings_frame = ttk.LabelFrame(general_frame, text="Application Settings", padding="10")
        app_settings_frame.grid(row=general_row, column=0, sticky="ew", pady=(0, 10))
        app_settings_frame.grid_columnconfigure(1, weight=1)
        general_row += 1

        # Theme Selection
        ttk.Label(app_settings_frame, text="Theme:").grid(row=settings_row, column=0, sticky=tk.W, pady=2, padx=(0, 5))
        theme_var = tk.StringVar(value=self.settings.theme)
        theme_combo = ttk.Combobox(app_settings_frame, textvariable=theme_var, values=["dark", "light"], state="readonly", width=18)
        theme_combo.grid(row=settings_row, column=1, sticky=tk.W, pady=2)
        settings_row += 1

        # Notification Sound
        notif_sound_var = tk.BooleanVar(value=self.settings.notification_sound)
        ttk.Checkbutton(app_settings_frame, text="Notification Sound", variable=notif_sound_var).grid(row=settings_row, column=0, columnspan=2, sticky=tk.W, pady=2)
        settings_row += 1

        # Minimize to Tray
        minimize_var = tk.BooleanVar(value=self.settings.minimize_to_tray)
        ttk.Checkbutton(app_settings_frame, text="Minimize to Tray", variable=minimize_var).grid(row=settings_row, column=0, columnspan=2, sticky=tk.W, pady=2)
        settings_row += 1

        # Formula Screenshot Pipeline
        formula_pipeline_var = tk.BooleanVar(value=self.settings.formula_screenshot_pipeline)
        formula_cb = ttk.Checkbutton(app_settings_frame, text="Formula support for Screenshot (Experimental, uses Gemini)", variable=formula_pipeline_var)
        formula_cb.grid(row=settings_row, column=0, columnspan=2, sticky=tk.W, pady=2)
        settings_row += 1

        # Debug Mode (Checkbox only, Log appears separately)
        debug_var = tk.BooleanVar(value=self.settings.debug_mode)
        debug_cb = ttk.Checkbutton(app_settings_frame, text="Show Debug Log", variable=debug_var)
        debug_cb.grid(row=settings_row, column=0, columnspan=2, sticky=tk.W, pady=2)
        settings_row += 1

        # Language (Variable defined for saving, UI commented out)
        lang_var = tk.StringVar(value=self.settings.language)

        # Document Folder Selection
        folder_frame = ttk.Frame(app_settings_frame)
        folder_frame.grid(row=settings_row, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=2)
        folder_frame.grid_columnconfigure(1, weight=1)
        settings_row += 1

        ttk.Label(folder_frame, text="Documents Folder:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        folder_var = tk.StringVar(value=self.settings.documents_folder)
        folder_entry = ttk.Entry(folder_frame, textvariable=folder_var, state="readonly")
        folder_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5)

        def browse_folder():
            folder = filedialog.askdirectory(initialdir=folder_var.get())
            if folder:
                folder = ensure_clipbrd_folder(folder)
                folder_var.set(folder)

        folder_button_frame = ttk.Frame(folder_frame)
        folder_button_frame.grid(row=0, column=2)
        ttk.Button(folder_button_frame, text="Browse", command=browse_folder).grid(row=0, column=0, padx=2)

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
        ttk.Button(folder_button_frame, text="Open", command=open_current_folder).grid(row=0, column=1, padx=2)


        # --- Shortcuts Frame ---
        shortcut_row = 0
        shortcuts_frame = ttk.LabelFrame(general_frame, text="Shortcuts", padding="10")
        shortcuts_frame.grid(row=general_row, column=0, sticky="ew", pady=(0, 10))
        shortcuts_frame.grid_columnconfigure(1, weight=1)
        general_row += 1

        # Full Screenshot Shortcut
        ttk.Label(shortcuts_frame, text="Full Screen Screenshot:").grid(row=shortcut_row, column=0, padx=(0,5), pady=2, sticky='w')
        full_shortcut_var = tk.StringVar(value=self.settings.shortcuts.get("full_screenshot", "<ctrl>+<shift>+f"))
        full_shortcut_entry = ttk.Entry(shortcuts_frame, textvariable=full_shortcut_var, width=20)
        full_shortcut_entry.grid(row=shortcut_row, column=1, padx=5, pady=2, sticky='w')
        shortcut_row += 1

        # Reset Icon Shortcut
        ttk.Label(shortcuts_frame, text="Reset Icon:").grid(row=shortcut_row, column=0, padx=(0,5), pady=2, sticky='w')
        reset_shortcut_var = tk.StringVar(value=self.settings.shortcuts.get("reset_icon_shortcut", "<ctrl>+<shift>+i"))
        reset_shortcut_entry = ttk.Entry(shortcuts_frame, textvariable=reset_shortcut_var, width=20)
        reset_shortcut_entry.grid(row=shortcut_row, column=1, padx=5, pady=2, sticky='w')
        shortcut_row += 1
        # Add other screenshot shortcuts here if needed


        # --- Debug Log Frame (Conditional Display) ---
        debug_log_frame = ttk.LabelFrame(general_frame, text="Debug Log", padding="10")
        # Grid positioning is handled by on_debug_toggle

        debug_log_frame.grid_columnconfigure(0, weight=1)
        debug_log_frame.grid_rowconfigure(0, weight=1) # Allow text area to expand

        debug_text = tk.Text(debug_log_frame, height=10, width=60, wrap=tk.WORD)
        debug_scrollbar = ttk.Scrollbar(debug_log_frame, orient="vertical", command=debug_text.yview)
        debug_text.configure(yscrollcommand=debug_scrollbar.set)
        debug_text.grid(row=0, column=0, sticky="nsew")
        debug_scrollbar.grid(row=0, column=1, sticky="ns")

        debug_button_frame = ttk.Frame(debug_log_frame)
        debug_button_frame.grid(row=1, column=0, columnspan=2, pady=(5,0), sticky='ew')
        # Center buttons using pack within the frame
        clear_button = ttk.Button(debug_button_frame, text="Clear", command=lambda: debug_text.delete(1.0, tk.END))
        clear_button.pack(side=tk.LEFT, padx=5)

        def update_debug_log():
            if not debug_var.get(): return
            try:
                log_file = self.app_data_dir / "debug.log"
                if log_file.exists():
                    with open(log_file, 'r', encoding='utf-8') as f:
                        lines = f.readlines()[-100:] # Show last 100 lines
                        debug_text.delete(1.0, tk.END)
                        debug_text.insert(tk.END, "".join(lines))
                        debug_text.see(tk.END)
                else:
                    debug_text.delete(1.0, tk.END)
                    debug_text.insert(tk.END, "Debug log file not found.")
            except Exception as e:
                logger.warning(f"Error reading debug log: {e}")
                debug_text.delete(1.0, tk.END)
                debug_text.insert(tk.END, f"Error reading debug log: {str(e)}")

        refresh_button = ttk.Button(debug_button_frame, text="Refresh", command=update_debug_log)
        refresh_button.pack(side=tk.LEFT, padx=5)

        # --- Save Settings Function (Define before used by button and toggle logic) ---
        def save_settings_action(): # Renamed to avoid conflict with class method
            try:
                # 1. Update settings object from UI variables
                self.settings.debug_mode = debug_var.get()
                self.settings.theme = theme_var.get()
                self.settings.notification_sound = notif_sound_var.get()
                self.settings.minimize_to_tray = minimize_var.get()
                self.settings.formula_screenshot_pipeline = formula_pipeline_var.get()
                self.settings.language = lang_var.get() # Save even if UI commented
                self.settings.documents_folder = folder_var.get()

                # Update shortcuts in the settings object's dictionary
                current_shortcuts = self.settings.shortcuts if self.settings.shortcuts else {}
                current_shortcuts["full_screenshot"] = full_shortcut_var.get()
                current_shortcuts["reset_icon_shortcut"] = reset_shortcut_var.get()
                self.settings.shortcuts = current_shortcuts # Assign back

                # 2. Persist shortcuts using the dedicated save_shortcuts function
                save_shortcuts(self.settings.shortcuts)

                # 3. Persist all settings to settings.json
                save_successful = self.save_settings() # Call the SettingsManager method

                if save_successful:
                    messagebox.showinfo("Success", "Settings saved successfully!")
                else:
                    messagebox.showerror("Error", "Failed to save settings to file.")

            except Exception as e:
                messagebox.showerror("Error", f"Failed to save settings: {e}")
                logger.error(f"Failed to save settings: {e}", exc_info=True)
            finally:
                on_closing() # Close dialog

        # --- Create Save Button (Before on_debug_toggle needs it) ---
        save_button = ttk.Button(general_frame, text="Save Settings", command=save_settings_action)
        # Grid placement happens inside on_debug_toggle

        # --- Define Debug Toggle Logic ---
        def on_debug_toggle():
            current_debug_row = general_row # Capture the row where debug log *would* go
            if debug_var.get():
                debug_log_frame.grid(row=current_debug_row, column=0, sticky='nsew', pady=(0, 10))
                general_frame.grid_rowconfigure(current_debug_row, weight=1)
                update_debug_log()
                save_button_row = current_debug_row + 1 # Place save button below log
            else:
                debug_log_frame.grid_remove()
                general_frame.grid_rowconfigure(current_debug_row, weight=0)
                save_button_row = current_debug_row # Place save button where log would have been

            # Adjust save button position
            save_button.grid(row=save_button_row, column=0, pady=(10, 0), sticky='ew')

        # --- Final Setup ---
        debug_cb.config(command=on_debug_toggle) # Set the command after button and function are defined
        on_debug_toggle() # Call initially to set visibility and save button position

        def auto_update_debug():
            if root.winfo_exists() and debug_var.get():
                update_debug_log()
                root.after(2000, auto_update_debug)
        auto_update_debug()

        # Remove the previous save button creation/grid call as it's now handled above
        # --- Save Button --- (Position adjusted by on_debug_toggle)
        # save_button = ttk.Button(general_frame, text="Save Settings", command=None) # Command set later

        # Assign command to save button (already done above)
        # save_button.config(command=save_settings_action)

        # === Other Tabs (Placeholder) ===
        # advanced_frame = ttk.Frame(notebook, padding="10")
        # notebook.add(advanced_frame, text="Advanced")

        try:
            # Let the window determine its size initially
            root.update_idletasks()
            # Optional: Set a minimum size
            # root.minsize(root.winfo_reqwidth(), root.winfo_reqheight())

            root.mainloop()
        except Exception as e:
            logger.error(f"Error in settings dialog mainloop: {e}", exc_info=True)
            self.settings_window = None # Ensure reference is cleared
            try:
                if root.winfo_exists(): root.destroy()
            except: pass # Ignore destroy errors