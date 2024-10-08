import os
import threading
import time
import rumps
import clipman
import requests
from io import BytesIO
from PIL import Image

from clipboard_processing import check_clipboard, check_screenshot
from document_processing import search
from screenshot import load_shortcuts, save_shortcuts, take_screenshot
from utils import create_text_image

clipman.init()

class ClipbrdApp(rumps.App):
    def __init__(self, llm_router, documents, inverted_index, terminate_event):
        super(ClipbrdApp, self).__init__("Clipbrd")
        self.menu = [
            "Take Full Screen Screenshot",
            "Configure Keyboard Shortcuts",
            "Register Program",
            "View Debug Info"
        ]
        self.keep_running = True
        self.last_clipboard = ""
        self.question_clipboard = ""
        clipman.copy("")
        self.debug_info = []
        self.llm_router = llm_router
        self.documents = documents
        self.inverted_index = inverted_index
        self.screenshot = None
        self.terminate_event = terminate_event
        self.search = search

        self.clipboard_check_thread = threading.Thread(target=self.clipboard_check_loop)
        self.clipboard_check_thread.start()

    @rumps.clicked("Take Full Screen Screenshot")
    def take_full_screenshot(self, _):
        self.update_title("Clipbrd: Taking Screenshot.")
        self.screenshot = take_screenshot()

    @rumps.clicked("Configure Keyboard Shortcuts")
    def configure_keyboard_shortcuts(self, _):
        shortcuts = load_shortcuts()
        response = rumps.Window(
            "Enter Full Screenshot Shortcut:",
            default_text=shortcuts.get("full_screenshot", ""),
            ok="Save",
            cancel="Cancel"
        ).run()
        if response.clicked:
            shortcuts = {"full_screenshot": response.text}
            save_shortcuts(shortcuts)

    @rumps.clicked("Register Program")
    def register_program(self, _):
        rumps.alert("Program Registration", "Registration placeholder")

    @rumps.clicked("View Debug Info")
    def show_debug_info(self, _):
        debug_text = "\n".join(self.debug_info)
        rumps.alert("Debug Info", debug_text)

    def update_title(self, text):
        self.title = text

    def on_screenshot(self, image):
        if self.title != "Clipbrd: Taking Screenshot.":
            self.update_title("Clipbrd: Taking Screenshot.")
        self.screenshot = image

    def clipboard_check_loop(self):
        while self.keep_running and not self.terminate_event.is_set():
            check_clipboard(self)
            check_screenshot(self)
            time.sleep(1)

    def stop(self):
        self.keep_running = False
        self.terminate_event.set()
        
        if self.clipboard_check_thread.is_alive():
            self.clipboard_check_thread.join()
        
        for thread in threading.enumerate():
            if thread.name.startswith("screenshot_thread"):
                thread.join()
        
        rumps.quit_application()