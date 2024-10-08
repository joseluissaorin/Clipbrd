import os
import sys
import json
import tkinter as tk
import io
import base64
from pynput import keyboard, mouse
from PIL import ImageGrab, Image
import threading

def setup_custom_screenshot_shortcut(callback, shortcut_key, terminate_event=None):
    def on_activate():
        if callback.__name__ == 'take_full_screenshot':
            screenshot = take_screenshot()
            callback(None, None)  # Call take_full_screenshot with None arguments
        else:
            screenshot = take_screenshot()
            callback(screenshot)

    if sys.platform == 'darwin':  # macOS
        keyboard_thread = threading.Thread(target=keyboard.GlobalHotKeys, args=({shortcut_key: on_activate},), kwargs={"terminate_event": terminate_event})
        keyboard_thread.name = f"screenshot_thread_{callback.__name__}"
        keyboard_thread.daemon = True
        keyboard_thread.start()
    else:  # Windows or other platforms
        with keyboard.GlobalHotKeys({shortcut_key: on_activate}, terminate_event=terminate_event) as h:
            h.join()

def take_screenshot():
    screenshot = ImageGrab.grab()
    buffered = io.BytesIO()
    screenshot.save(buffered, format="PNG")
    base64_screenshot = base64.b64encode(buffered.getvalue()).decode('utf-8')
    return base64_screenshot

def save_shortcuts(shortcuts):
    config_path = os.path.join(os.path.expanduser("~"), ".clipbrd", "config.json")
    os.makedirs(os.path.dirname(config_path), exist_ok=True)

    existing_config = load_shortcuts()
    existing_config.update(shortcuts)

    with open(config_path, "w") as f:
        json.dump(existing_config, f)

def load_shortcuts():
    config_path = os.path.join(os.path.expanduser("~"), ".clipbrd", "config.json")

    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            config = json.load(f)
            return config
    else:
        return {
            "predefined_screenshot": "<ctrl>+<shift>+p",
            "custom_screenshot": "<ctrl>+<shift>+l",
            "full_screenshot": "<ctrl>+<shift>+f"
        }
    
