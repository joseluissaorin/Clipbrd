# gui_part.py
import tkinter as tk
from screenshot import select_region, save_predefined_region, load_shortcuts, save_shortcuts, take_screenshot

class GuiPart(object):
    def __init__(self, master, queue):
        self.queue = queue
        self.master = master

    def processIncoming(self):
        """ Handle all messages currently in the queue, if any. """
        while self.queue.qsize():
            try:
                msg = self.queue.get_nowait()
                if msg[0] == "show_debug_info":
                    self.show_debug_info(msg[1])
                elif msg[0] == "configure_keyboard_shortcuts":
                    self.configure_keyboard_shortcuts()
                elif msg[0] == "define_preconfigured_region":
                    self.define_preconfigured_region()
                elif msg[0] == "select_region_and_screenshot":
                    self.select_region_and_screenshot()
            except self.queue.Empty:
                pass

    def show_debug_info(self, debug_info):
        window = tk.Toplevel(self.master)
        window.title("Debug Info")
        text_area = tk.Text(window, width=60, height=20, wrap="word")
        text_area.pack(padx=10, pady=10, fill="both", expand=True)
        debug_text = "\n".join(debug_info)
        text_area.insert("1.0", debug_text)
        text_area.configure(state="disabled")

    def configure_keyboard_shortcuts(self):
        def save_shortcuts_cmd():
            shortcut1 = shortcut1_entry.get()
            shortcut2 = shortcut2_entry.get()
            if shortcut1 == None and shortcut2 != None:
                shortcuts = {
                    "predefined_screenshot": "<ctrl>+<shift>+p",
                    "custom_screenshot": shortcut2
                }
            elif shortcut1 != None and shortcut2 == None:
                shortcuts = {
                    "predefined_screenshot": shortcut1,
                    "custom_screenshot": "<ctrl>+<shift>+l"
                }
            elif shortcut1 == None and shortcut2 == None:
                shortcuts = {
                    "predefined_screenshot": "<ctrl>+<shift>+p",
                    "custom_screenshot": "<ctrl>+<shift>+l"
                }
            save_shortcuts(shortcuts)
            window.destroy()

        shortcuts = load_shortcuts()

        window = tk.Toplevel(self.master)
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

    def define_preconfigured_region(self):
        region = select_region()
        if region:
            save_predefined_region(region)

    def select_region_and_screenshot(self):
        region = select_region()
        if region is not None:
            self.queue.put(("on_screenshot", take_screenshot(region=region)))