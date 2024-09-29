# windows_app.py
import os
import threading
import time
import tkinter as tk
from io import BytesIO

import clipman
import pystray
import requests
from PIL import Image, ImageGrab
from pystray import MenuItem as item

from clipboard_processing import check_clipboard, check_screenshot
from document_processing import search
from screenshot import load_shortcuts, save_shortcuts, take_screenshot
from utils import create_text_image

clipman.init()

class ClipbrdApp:
    def __init__(self, llm_router, documents, inverted_index, terminate_event):
        self.icon = pystray.Icon("Clipbrd")
        self.keep_running = True
        self.icon.menu = pystray.Menu(
            item('Take Full Screen Screenshot', self.take_full_screenshot),
            item('Configure Keyboard Shortcuts', self.configure_keyboard_shortcuts),
            item('Register Program', self.register_program),
            item('View Debug Info', self.show_debug_info),
            item('Quit', self.quit_icon)
        )
        self.last_clipboard = ""
        self.question_clipboard = ""
        clipman.copy("")
        self.update_icon("Clipbrd")
        self.debug_info = []
        self.llm_router = llm_router
        self.documents = documents
        self.inverted_index = inverted_index
        self.screenshot = None
        self.terminate_event = terminate_event
        self.search = search
    
    def update_icon(self, text):
        if text == "Clipbrd":
            response = requests.get(
                "https://img.joseluissaorin.com/clipbrd_logo_4.png")
            image_stream = BytesIO(response.content)
            self.icon.icon = Image.open(image_stream)
        elif text == "Clipbrd: Done.":
            self.icon.icon = create_text_image(
                "✅", background_color=(255, 0, 0, 0))
        elif text == "Clipbrd: Working.":
            self.icon.icon = create_text_image(
                "⛏️", background_color=(255, 0, 0, 0))
        else:
            self.icon.icon = create_text_image(text.split(
                ':')[-1], background_color=(255, 0, 0, 0))

    def on_screenshot(self, image):
        self.screenshot = image

    def show_debug_info(self, sender):
        window = tk.Tk()
        window.title("Debug Info")
        text_area = tk.Text(window, width=60, height=20, wrap="word")
        text_area.pack(padx=10, pady=10, fill="both", expand=True)
        debug_text = "\n".join(self.debug_info)
        text_area.insert("1.0", debug_text)
        text_area.configure(state="disabled")
        window.mainloop()

    def take_full_screenshot(self, icon, item):
        self.screenshot = take_screenshot()

    def configure_keyboard_shortcuts(self, icon, item):
        def save_shortcuts_cmd():
            shortcut = shortcut_entry.get()
            shortcuts = {
                "full_screenshot": shortcut
            }
            save_shortcuts(shortcuts)
            window.destroy()

        shortcuts = load_shortcuts()

        window = tk.Tk()
        window.title("Configure Keyboard Shortcuts")

        tk.Label(window, text="Full Screenshot Shortcut:").grid(row=0, column=0, padx=5, pady=5)
        shortcut_entry = tk.Entry(window)
        shortcut_entry.insert(0, shortcuts.get("full_screenshot", ""))
        shortcut_entry.grid(row=0, column=1, padx=5, pady=5)

        save_button = tk.Button(window, text="Save", command=save_shortcuts_cmd)
        save_button.grid(row=1, column=0, columnspan=2, padx=5, pady=5)

        window.mainloop()

    def register_program(self, icon, item):
        def close_window():
            window.destroy()

        window = tk.Tk()
        window.title("Register Program")
        window.geometry("300x150")

        label = tk.Label(window, text="Program Registration")
        label.pack(pady=20)

        placeholder_text = tk.Label(window, text="Registration placeholder")
        placeholder_text.pack(pady=10)

        close_button = tk.Button(window, text="Close", command=close_window)
        close_button.pack(pady=10)

        window.mainloop()

    def quit_icon(self, icon, item):
        self.keep_running = False
        self.terminate_event.set()
        
        if self.clipboard_check_thread.is_alive():
            self.clipboard_check_thread.join()
        
        for thread in threading.enumerate():
            if thread.name.startswith("screenshot_thread"):
                thread.join()
        
        icon.stop()
        os._exit(0)

    def run(self):
        self.icon.run(self.setup)

    def setup(self, icon):
        icon.visible = True
        self.clipboard_check_thread = threading.Thread(target=self.clipboard_check_loop)
        self.clipboard_check_thread.start()

    def clipboard_check_loop(self):
        while self.keep_running and not self.terminate_event.is_set():
            check_clipboard(self)
            check_screenshot(self)
            time.sleep(1)