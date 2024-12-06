import os
import json
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
from license_manager import LicenseManager

logger = logging.getLogger(__name__)

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
    
    def __post_init__(self):
        if self.shortcuts is None:
            self.shortcuts = {
                "full_screenshot": "<ctrl>+<shift>+f",
                "region_screenshot": "<ctrl>+<shift>+r",
                "toggle_debug": "<ctrl>+<shift>+d"
            }

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
        """Show settings dialog."""
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
        
        # Get screen dimensions
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        
        # Initial size (will be adjusted later)
        window_width = min(int(screen_width * 0.4), 600)  # 40% of screen width, max 600px
        window_height = min(int(screen_height * 0.6), 800)  # 60% of screen height, max 800px
        
        # Calculate position
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        
        # Set initial geometry
        root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        # Make window resizable
        root.resizable(True, True)
        
        # Configure grid weights
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(0, weight=1)

        # Handle window close event
        def on_closing():
            try:
                self.settings_window = None
                root.destroy()
            except Exception as e:
                logger.error(f"Error closing settings window: {e}")
                try:
                    root.destroy()
                except:
                    pass

        root.protocol("WM_DELETE_WINDOW", on_closing)

        # Set window icon
        icon_path = os.path.join(os.path.dirname(__file__), 'assets', 'icons', 
                               'clipbrd_windows.ico' if os.name == 'nt' else 'clipbrd_macos.png')
        if os.path.exists(icon_path):
            if os.name == 'nt':
                root.iconbitmap(icon_path)
            else:
                img = Image.open(icon_path)
                photo = ImageTk.PhotoImage(img)
                root.iconphoto(True, photo)

        # Create main frame with scrolling capability
        canvas = tk.Canvas(root)
        scrollbar = ttk.Scrollbar(root, orient="vertical", command=canvas.yview)
        main_frame = ttk.Frame(canvas, padding="20")
        
        # Configure scrolling
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Pack scrollbar and canvas
        scrollbar.grid(row=0, column=1, sticky="ns")
        canvas.grid(row=0, column=0, sticky="nsew")
        
        # Create window in canvas for main frame
        canvas_window = canvas.create_window((0, 0), window=main_frame, anchor="nw")
        
        # Configure main frame grid
        main_frame.grid_columnconfigure(0, weight=1)
        
        # Update scroll region when main frame size changes
        def configure_scroll_region(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            # Update canvas window width to match canvas width
            canvas.itemconfig(canvas_window, width=canvas.winfo_width())
        
        main_frame.bind("<Configure>", configure_scroll_region)
        
        # Handle mouse wheel scrolling
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        canvas.bind_all("<MouseWheel>", on_mousewheel)

        # License Frame
        license_frame = ttk.LabelFrame(main_frame, text="License", padding="10")
        license_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 20))

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
        settings_frame = ttk.LabelFrame(main_frame, text="Settings", padding="10")
        settings_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
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

        # Language
        ttk.Label(settings_frame, text="Language:").grid(row=4, column=0, sticky=tk.W, pady=5)
        lang_var = tk.StringVar(value=self.settings.language)
        lang_combo = ttk.Combobox(settings_frame, textvariable=lang_var, values=["en", "es", "fr", "de"], state="readonly")
        lang_combo.grid(row=4, column=1, sticky=tk.W, pady=5)

        def save_settings():
            try:
                self.settings.debug_mode = debug_var.get()
                self.settings.notification_sound = notif_sound_var.get()
                self.settings.minimize_to_tray = minimize_var.get()
                self.settings.language = lang_var.get()
                self.save_settings()
            finally:
                on_closing()

        # Save Button
        ttk.Button(main_frame, text="Save", command=save_settings).grid(row=2, column=0, pady=20)

        try:
            root.mainloop()
        except Exception as e:
            logger.error(f"Error in settings dialog: {e}")
            self.settings_window = None
            try:
                root.destroy()
            except:
                pass