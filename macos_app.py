import base64
import io
import time
import threading
import rumps
import clipman
import tkinter as tk
from utils import create_text_image
from ocr import ocr_image, is_question_with_image
from question_processing import is_formatted_question, get_answer_with_context, get_number_with_context, get_number_without_context, get_number_with_image, get_answer_without_context
from search import search
from screenshot import select_region, save_predefined_region, take_screenshot, load_shortcuts, save_shortcuts

clipman.init()

class ClipbrdApp(rumps.App):
    def __init__(self, llm_router, documents, inverted_index, terminate_event):
        super(ClipbrdApp, self).__init__("Clipbrd")
        self.keep_running = True
        self.last_clipboard = ""
        self.question_clipboard = ""
        clipman.copy("")
        self.title = "Clipbrd"
        self.llm_router = llm_router
        self.documents = documents
        self.inverted_index = inverted_index
        self.screenshot = None
        self.terminate_event = terminate_event
        self.debug_info = []
        self.menu = [
            rumps.MenuItem('Define Preconfigured Region', callback=self.define_preconfigured_region),
            rumps.MenuItem('Select Region and Screenshot', callback=self.select_region_and_screenshot),
            rumps.MenuItem('Configure Keyboard Shortcuts', callback=self.configure_keyboard_shortcuts),
            rumps.MenuItem('View Debug Info', callback=self.show_debug_info),
            #rumps.MenuItem('Quit', callback=rumps.quit_application)
        ]

    def update_icon(self, text):
        self.title = text

    def on_screenshot(self, image):
        self.screenshot = image

    def check_screenshot(self):
        if self.screenshot is not None:
            # Convert screenshot to base64
            buffered = io.BytesIO()
            self.screenshot.save(buffered, format="PNG")
            base64_image = base64.b64encode(buffered.getvalue()).decode('utf-8')
            base64_image_url = f"data:image/png;base64,{base64_image}"

            # Determine if it is a question with an image or just text
            if is_question_with_image(base64_image_url, self.llm_router):
                # Process question with image
                self.debug_info.append("Processing question with image")

                # Create the image data dictionary
                image_data = {
                    "url": f"data:image/png;base64,{base64_image}",
                    "detail": "high"
                }

                answer_number = get_number_with_image("Answer the following question", self.llm_router, image_data=image_data)
                self.update_icon(f"Clipbrd: {answer_number}")
                self.debug_info.append(f"MCQ answer with image: {answer_number}")
            else:
                # Process image without question
                ocr_text = ocr_image(image_64=base64_image)
                self.debug_info.append(f"OCR Text: {ocr_text}")

                is_mcq, clipboard = is_formatted_question(ocr_text, self.llm_router)
                self.debug_info.append(f"MCQ detected: {is_mcq}")
                if is_mcq:
                    answer_number = get_number_with_context(clipboard, self.llm_router, search, self.inverted_index, self.documents)
                    if answer_number is None:
                        answer_number = get_number_without_context(clipboard, self.llm_router)
                    self.update_icon(f"Clipbrd: {answer_number}")
                    self.debug_info.append(f"MCQ answer: {answer_number}")
                else:
                    self.update_icon("Clipbrd: Working.")
                    self.debug_info.append("Processing non-MCQ question")
                    answer = get_answer_with_context(clipboard, self.llm_router, search, self.inverted_index, self.documents)
                    if answer is None:
                        answer = get_answer_without_context(clipboard, self.llm_router)
                    self.question_clipboard = answer
                    self.update_icon("Clipbrd: Done.")
                    self.debug_info.append(f"Answer: {answer}")

            self.screenshot = None

    def show_debug_info(self, sender):
            window = tk.Tk()
            window.title("Debug Info")
            text_area = tk.Text(window, width=60, height=20, wrap="word")
            text_area.pack(padx=10, pady=10, fill="both", expand=True)
            debug_text = "\n".join(self.debug_info)
            text_area.insert("1.0", debug_text)
            text_area.configure(state="disabled")
            window.mainloop()

    def define_preconfigured_region(self, icon=None, item=None):
        print("Hola")
        region = select_region()
        if region:
            save_predefined_region(region)

    def select_region_and_screenshot(self, icon=None, item=None):
        region = select_region()
        print(region)
        if region is not None:
            self.on_screenshot(take_screenshot(region=region))

    def configure_keyboard_shortcuts(self, icon=None, item=None):
        def save_shortcuts_cmd():
            shortcut1 = shortcut1_entry.get()
            shortcut2 = shortcut2_entry.get()
            shortcuts = {
                "predefined_screenshot": shortcut1,
                "custom_screenshot": shortcut2
            }
            save_shortcuts(shortcuts)
            window.destroy()

        shortcuts = load_shortcuts()

        window = tk.Tk()
        window.title("Configure Keyboard Shortcuts")

        tk.Label(window, text="Predefined Screenshot Shortcut:").grid(row=0, column=0, padx=5, pady=5)
        shortcut1_entry = tk.Entry(window)
        shortcut1_entry.insert(0, shortcuts.get("predefined_screenshot", ""))
        shortcut1_entry.grid(row=0, column=1, padx=5, pady=5)

        tk.Label(window, text="Custom Screenshot Shortcut:").grid(row=1, column=0, padx=5, pady=5)
        shortcut2_entry = tk.Entry(window)
        shortcut2_entry.insert(0, shortcuts.get("custom_screenshot", ""))
        shortcut2_entry.grid(row=1, column=1, padx=5, pady=5)

        save_button = tk.Button(window, text="Save", command=save_shortcuts_cmd)
        save_button.grid(row=2, column=0, columnspan=2, padx=5, pady=5)

        window.mainloop()

    def check_clipboard(self):
        current_clipboard = clipman.paste()
        if current_clipboard != self.last_clipboard and current_clipboard != self.question_clipboard:
            self.last_clipboard = current_clipboard
            self.debug_info.append(f"Clipboard content: {current_clipboard}")

            # Process clipboard content
            is_mcq, clipboard = is_formatted_question(current_clipboard, self.llm_router)
            self.debug_info.append(f"MCQ detected: {is_mcq}")
            if is_mcq:
                self.update_icon("Clipbrd: Working.")
                answer_number = get_number_with_context(current_clipboard, self.llm_router, search, self.inverted_index, self.documents)
                if answer_number is None:
                    answer_number = get_number_without_context(current_clipboard, self.llm_router)
                self.update_icon(f"Clipbrd: {answer_number}")
                self.debug_info.append(f"MCQ answer: {answer_number}")
                self.last_clipboard = clipboard
            else:
                self.update_icon("Clipbrd: Working.")
                self.debug_info.append("Processing non-MCQ question")
                answer = get_answer_with_context(current_clipboard, self.llm_router, search, self.inverted_index, self.documents)
                self.debug_info.append(f"Answer with context: {answer}")
                if answer is None:
                    answer = get_answer_without_context(current_clipboard, self.llm_router)
                    self.debug_info.append(f"Answer without context: {answer}")
                self.question_clipboard = answer
                clipman.copy(answer)
                self.update_icon("Clipbrd: Done.")
                self.debug_info.append(f"Answer: {answer}")

    
    def quit_icon(self, sender):
        self.keep_running = False
        self.terminate_event.set()
        rumps.quit_application()

    @rumps.timer(1)
    def clipboard_check_loop(self, _=None):
        if self.keep_running:
            self.check_clipboard()
            self.check_screenshot()

    def run(self):
        threading.Thread(target=self.clipboard_check_loop).start()
        rumps.App.run(self)