import os
import pypandoc 
import sys
from PIL import Image, ImageFont
from pilmoji import Pilmoji
from pathlib import Path

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
        pilmoji.text((x, y), text, fill=text_color, font=font, emoji_position_offset=(0, -58), emoji_scale_factor=1)

    return image

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def download_pandoc():
    # Check if Pandoc is already installed
    try:
        version = pypandoc.get_pandoc_version()
        # print(f"Pandoc already installed, version: {version}")
    except OSError:
        # print("Downloading Pandoc...")
        pypandoc.pandoc_download.download_pandoc()