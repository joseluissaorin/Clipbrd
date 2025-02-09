import os
import logging
import pypandoc 
import sys
from PIL import Image, ImageFont, ImageDraw
from pilmoji import Pilmoji
from pathlib import Path
from emoji_source import AlternativeCDNSource

logger = logging.getLogger(__name__)

def get_cache_dir() -> str:
    """Get the emoji cache directory path based on execution context."""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # Running as compiled executable
        base_path = sys._MEIPASS
    else:
        # Running from source
        base_path = os.path.dirname(__file__)
    
    cache_dir = os.path.join(base_path, 'cache', 'emojis')
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir

def initialize_emoji_source() -> AlternativeCDNSource:
    """Initialize and verify the emoji source with cache."""
    cache_dir = get_cache_dir()
    source = AlternativeCDNSource(cache_dir=cache_dir)
    
    # Verify cache integrity
    is_valid, verification_results = source.verify_cache()
    if not is_valid:
        logger.warning("Emoji cache verification failed")
        total_issues = len(verification_results['missing']) + len(verification_results['corrupted'])
        logger.info(f"Attempting to repair {total_issues} cache issues")
        
        # Attempt to repair cache
        if source.repair_cache(verification_results):
            logger.info("Cache repair successful")
        else:
            logger.warning("Some cache repairs failed - will attempt to fetch missing emojis at runtime")
    else:
        logger.info("Emoji cache verification successful")
    
    return source

# Initialize emoji source with caching and verification
emoji_source = initialize_emoji_source()

def create_text_image(text, width=72, height=72, background_color='black', text_color='white', font_path="arial.ttf", font_size=64):
    """Create an image with text and emojis using the alternative CDN source."""
    try:
        # Create an image with specified background color
        image = Image.new('RGBA', (width, height), background_color)
        
        # Use a truetype font
        font = ImageFont.truetype(font_path, font_size)
        
        try:
            # Create a fresh emoji source for each call
            local_emoji_source = initialize_emoji_source()
            
            # Try with emoji support first
            pilmoji = Pilmoji(image, source=local_emoji_source)
            
            # Calculate text size using font.getbbox
            bbox = font.getbbox(text)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            # Calculate position to center the text
            x = int((width - text_width) / 2)
            y = int((height - text_height) / 2)
            
            # Draw the text (with emojis) on the image
            pilmoji.text(
                (x, y), 
                text, 
                fill=text_color, 
                font=font, 
                emoji_position_offset=(0, -58), 
                emoji_scale_factor=1
            )
            logger.debug(f"Created image with emojis: {text}")
            
            # Create a copy of the image before closing pilmoji
            result_image = image.copy()
            pilmoji.close()
            
            return result_image
            
        except Exception as e:
            logger.warning(f"Failed to render with emojis, falling back to text-only: {e}")
            # Fallback to text-only if emoji rendering fails
            draw = ImageDraw.Draw(image)
            
            # Calculate text size using font.getbbox (new Pillow method)
            bbox = font.getbbox(text)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            # Center the text
            x = int((width - text_width) / 2)
            y = int((height - text_height) / 2)
            
            # Draw text without emojis
            draw.text((x, y), text, fill=text_color, font=font)
            logger.info(f"Created text-only image: {text}")
            
            return image
        
    except Exception as e:
        logger.error(f"Failed to create text image: {e}")
        # Create a simple error indicator image
        image = Image.new('RGBA', (width, height), background_color)
        draw = ImageDraw.Draw(image)
        draw.text((10, height//2), "!", fill=text_color, font=font)
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