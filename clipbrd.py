# clipbrd.py
# Standard library imports
import os
import sys
import threading
import queue
from glob import glob

# Third-party imports
# (None in this selection)

# Local application imports
from windows_app import ClipbrdApp
from llmrouter import LLMRouter
from utils import download_pandoc
from document_processing import process_documents
from screenshot import (
    setup_custom_screenshot_shortcut,
    load_shortcuts
)

# Setup LLMRouter
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

llm_router = LLMRouter(
   anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
   openai_api_key=os.environ.get("OPENAI_API_KEY"),
   deepinfra_api_key=os.environ.get("DEEPINFRA_API_KEY")
)

# Get the user's Documents folder path
documents_folder = os.path.expanduser("~/Documents")
if not os.path.exists(documents_folder):
   documents_folder = glob(os.path.expanduser("~\\*\\Documents"))  # For Windows with OneDrive
if not os.path.exists(documents_folder):
   documents_folder = glob(os.path.expanduser("~\\*\\Documentos"))  # For Spanish Windows with OneDrive
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

if __name__ == "__main__":
   # Download Data
   download_pandoc()

   # Process documents on app start
   documents, inverted_index = process_documents(clipbrd_folder)

   # Create a threading event for terminating the threads
   terminate_event = threading.Event()

   # Load shortcuts from file
   shortcuts = load_shortcuts()

   # Create a queue for Tkinter tasks
   tk_queue = queue.Queue()

      # Instantiate Clipbrd Class
   app = ClipbrdApp(llm_router, documents, inverted_index, terminate_event)
   
   # Setup screenshot shortcuts
   threading.Thread(target=setup_custom_screenshot_shortcut, args=(app.on_screenshot, shortcuts.get("full_screenshot"), terminate_event)).start()

   app.run()