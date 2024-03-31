# clipbrd.py
import os
import sys
import threading
import queue
from utils import download_nltk_data, download_pandoc, download_tesseract_data
from dotenv import load_dotenv
from llmrouter import LLMRouter
from document_processing import process_documents, build_inverted_index
from screenshot import setup_screenshot_shortcut, setup_custom_screenshot_shortcut, load_predefined_region, load_shortcuts

# Load environment variables from .env file
load_dotenv()

# Setup LLMRouter
llm_router = LLMRouter(
   anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
   openai_api_key=os.environ.get("OPENAI_API_KEY"),
   together_api_key=os.environ.get("TOGETHER_API_KEY")
)

# Get the user's Documents folder path
documents_folder = os.path.expanduser("~/Documents")
if not os.path.exists(documents_folder):
   documents_folder = os.path.expanduser("~/OneDrive/Documents")  # For Windows with OneDrive
if not os.path.exists(documents_folder):
   documents_folder = os.path.expanduser("~/Library/Documents")  # For macOS
if not os.path.exists(documents_folder):
   documents_folder = os.path.expanduser("~/Documentos")  # For Spanish language systems

# Create the Clipbrd folder in the user's Documents directory if it doesn't exist
clipbrd_folder = os.path.join(documents_folder, "Clipbrd")
if not os.path.exists(clipbrd_folder):
   os.makedirs(clipbrd_folder)
   print(f"Created the folder {clipbrd_folder}")

# Global variables
documents = None
inverted_index = None

if sys.platform == 'darwin':
    from macos_app import ClipbrdApp
elif sys.platform == 'win32':
    download_tesseract_data()
    from windows_app import ClipbrdApp
else:
    raise OSError("Unsupported operating system.")

if __name__ == "__main__":
   # Download Data
   download_pandoc()

   download_nltk_data()

   # Process documents on app start
   documents = process_documents(clipbrd_folder)

   # Build the inverted index
   inverted_index = build_inverted_index(documents)

   # Create a threading event for terminating the threads
   terminate_event = threading.Event()

   # Load predefined region and shortcuts from file
   predefined_region = load_predefined_region()
   shortcuts = load_shortcuts()

   # Create a queue for Tkinter tasks
   tk_queue = queue.Queue()

      # Instantiate Clipbrd Class
   app = ClipbrdApp(llm_router, documents, inverted_index, terminate_event)
   
   # Setup screenshot shortcuts
   threading.Thread(target=setup_screenshot_shortcut, args=(app.on_screenshot, shortcuts.get("predefined_screenshot"), terminate_event)).start()
   threading.Thread(target=setup_custom_screenshot_shortcut, args=(app.on_screenshot, shortcuts.get("custom_screenshot"), terminate_event)).start()

   app.run()