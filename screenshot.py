import os
import sys
import json
import tkinter as tk
from pynput import keyboard, mouse
from PIL import ImageGrab, Image
import threading

def setup_screenshot_shortcut(callback, predefined_region=None, shortcut_key='<ctrl>+<shift>+p', terminate_event=None):
    def on_activate():
        screenshot = take_screenshot(predefined=True, region=predefined_region)
        callback(screenshot)

    if sys.platform == 'darwin':  # macOS
        keyboard_thread = threading.Thread(target=keyboard.GlobalHotKeys, args=({shortcut_key: on_activate},))
        keyboard_thread.daemon = True
        keyboard_thread.start()
        while not terminate_event.is_set():
            keyboard_thread.join(0.1)
    else:  # Windows or other platforms
        with keyboard.GlobalHotKeys({shortcut_key: on_activate}) as h:
            h.join()

def setup_custom_screenshot_shortcut(callback, shortcut_key='<ctrl>+<shift>+o', terminate_event=None):
    def on_activate():
        screenshot = take_screenshot(predefined=False)
        callback(screenshot)

    if sys.platform == 'darwin':  # macOS
        keyboard_thread = threading.Thread(target=keyboard.GlobalHotKeys, args=({shortcut_key: on_activate},))
        keyboard_thread.daemon = True
        keyboard_thread.start()
        while not terminate_event.is_set():
            keyboard_thread.join(0.1)
    else:  # Windows or other platforms
        with keyboard.GlobalHotKeys({shortcut_key: on_activate}) as h:
            h.join()

def take_screenshot(predefined=False, region=None):
    if predefined and region:
        screenshot = ImageGrab.grab(bbox=region)
    else:
        screenshot = ImageGrab.grab(bbox=select_region())

    return screenshot

def select_region():
    left, top, width, height = 0, 0, 0, 0

    root = tk.Tk()
    root.attributes('-fullscreen', True)
    root.attributes('-alpha', 0.3)

    canvas = tk.Canvas(root, highlightthickness=0, background="gray")
    canvas.pack(fill=tk.BOTH, expand=True)

    start_x, start_y = 0, 0
    rect_id = None

    def on_mouse_press(event):
        nonlocal start_x, start_y
        start_x, start_y = event.x, event.y

    def on_mouse_move(event):
        nonlocal rect_id
        if rect_id:
            canvas.delete(rect_id)
        rect_id = canvas.create_rectangle(start_x, start_y, event.x, event.y, outline="red", width=2)

    def on_mouse_release(event):
        nonlocal left, top, width, height
        left = min(start_x, event.x)
        top = min(start_y, event.y)
        width = abs(event.x - start_x)
        height = abs(event.y - start_y)
        root.destroy()

    canvas.bind("<ButtonPress-1>", on_mouse_press)
    canvas.bind("<B1-Motion>", on_mouse_move)
    canvas.bind("<ButtonRelease-1>", on_mouse_release)

    root.mainloop()

    return (left, top, left + width, top + height)

def save_predefined_region(region):

    # Define the path for the configuration file
    config_path = os.path.join(os.path.expanduser("~"), ".clipbrd", "config.json")
    
    # Ensure the directory for the configuration file exists
    os.makedirs(os.path.dirname(config_path), exist_ok=True)

    # Load shortcuts from the load_shortcuts function
    shortcuts = load_shortcuts()

    # Ensure load_shortcuts() returns a dictionary. If not, convert or handle appropriately.
    assert isinstance(shortcuts, dict), "load_shortcuts() must return a dictionary"

    # Merge predefined_region with the shortcuts dictionary
    config_data = {"predefined_region": region, **shortcuts}

    # Write the merged dictionary to the config file in JSON format
    with open(config_path, "w") as f:
        json.dump(config_data, f)

def load_predefined_region():
    config_path = os.path.join(os.path.expanduser("~"), ".clipbrd", "config.json")

    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            config = json.load(f)
            return config.get("predefined_region")

    return None

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
        config = {"predefined_screenshot": "<ctrl>+<shift>+p", "custom_screenshot": "<ctrl>+<shift>+l"}
        return config