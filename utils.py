import os
import platform
import requests
import zipfile
import pytesseract
import pypandoc
import nltk
from PIL import Image, ImageFont
from pilmoji import Pilmoji

def create_text_image(text, width=72, height=72, background_color='black', text_color='white', font_path="arial.ttf", font_size=64):
    # Create an image with specified background color
    image = Image.new('RGBA', (width, height), background_color)

    # Use a truetype font
    font = ImageFont.truetype(font_path, font_size)

    with Pilmoji(image) as pilmoji:
        # Calculate text width and height with pilmoji
        text_width, text_height = pilmoji.getsize(text, font)

        # Calculate position to center the text
        x = int((width - text_width) / 2)
        y = int((height - text_height) / 2)

        # Draw the text (with emojis) on the image
        pilmoji.text((x, y), text, fill=text_color, font=font)

    return image

def download_pandoc():
    # Check if Pandoc is already installed
    try:
        version = pypandoc.get_pandoc_version()
        print(f"Pandoc already installed, version: {version}")
    except OSError:
        print("Downloading Pandoc...")
        pypandoc.pandoc_download.download_pandoc()

def download_nltk_data():
   nltk_data_path = "./data/"
   if not os.path.exists(nltk_data_path):
       os.makedirs(nltk_data_path)
       print("Created NLTK data path")

   nltk.data.path.append(nltk_data_path)

   if not os.path.exists(os.path.join(nltk_data_path, "corpora/wordnet")):
       print("Downloading NLTK data...")
       nltk.download("wordnet", download_dir=nltk_data_path)
       print("NLTK data downloaded.")


def download_tesseract_data():
   tesseract_data_path = "./data/tesseract"
   if not os.path.exists(tesseract_data_path):
       os.makedirs(tesseract_data_path)
       print("Created Tesseract data path")

   system = platform.system()
   if system == "Windows":
       tesseract_url = "https://img.joseluissaorin.com/tesseract-windows.zip"
   elif system == "Darwin":
       return
   else:
       raise ValueError(f"Unsupported operating system: {system}")

   tesseract_zip_path = os.path.join(tesseract_data_path, "tesseract.zip")

   if not os.path.exists(os.path.join(tesseract_data_path, "tesseract")):
       print("Downloading Tesseract data...")
       response = requests.get(tesseract_url)
       with open(tesseract_zip_path, "wb") as f:
           f.write(response.content)

       with zipfile.ZipFile(tesseract_zip_path, "r") as zip_ref:
           zip_ref.extractall(os.path.join(tesseract_data_path, "tesseract"))

       os.remove(tesseract_zip_path)
       print("Tesseract data downloaded.")

   if system == "Windows":
       pytesseract.tesseract_cmd = os.path.join(
           tesseract_data_path, "tesseract", "tesseract.exe")
   elif system == "Darwin":
       pytesseract.tesseract_cmd = os.path.join(
           tesseract_data_path, "tesseract", "tesseract")
