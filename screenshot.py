import os
import sys
import json
import tkinter as tk
import io
import base64
from pynput import keyboard, mouse
from PIL import ImageGrab, Image
import threading

from ocr import compress_image_to_size

def setup_custom_screenshot_shortcut(callback, shortcut_key, terminate_event=None):
    def on_activate():
        if callback.__name__ == 'take_full_screenshot':
            screenshot = take_screenshot()
            callback(None, None)  # Call take_full_screenshot with None arguments
        else:
            screenshot = take_screenshot()
            callback(screenshot)

    try:
        hotkeys = keyboard.GlobalHotKeys({shortcut_key: on_activate})
        hotkeys.start()

        # Optionally handle termination
        if terminate_event:
            terminate_event.wait()
            hotkeys.stop()
    except Exception as e:
        print(f"Error setting up shortcut: {e}")

def take_screenshot():
    screenshot = ImageGrab.grab()
    buffered = io.BytesIO()
    screenshot.save(buffered, format="PNG")
    buffered.seek(0)
    compressed_screenshot = compress_image_to_size(buffered, 1024, 4096)
    base64_screenshot = base64.b64encode(compressed_screenshot).decode('utf-8')
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

    predefined_shortcuts = {
        "predefined_screenshot": "<ctrl>+<shift>+p",
        "custom_screenshot": "<ctrl>+<shift>+l",
        "full_screenshot": "<ctrl>+<shift>+f"
    }

    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            config = json.load(f)
            print(config)
            # Add predefined shortcuts if they are missing
            for key, value in predefined_shortcuts.items():
                if key not in config:
                    config[key] = value
            return config
    else:
        print("predefined")
        return predefined_shortcuts
    
