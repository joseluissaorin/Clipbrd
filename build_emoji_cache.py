import os
import sys
import logging
import asyncio
import json
from pathlib import Path
from typing import List, Dict
from emoji_source import AlternativeCDNSource

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('build_emoji_cache.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger('BuildEmojiCache')

# Common emojis to pre-cache
COMMON_EMOJIS = {
    "Status Icons": [
        "✅", "❌", "⚠️", "ℹ️", "🔄", "⏳", "🔍",
        "💡", "🔒", "🔓", "⭐", "📌", "🎯", "⚡"
    ],
    "Reactions": [
        "👍", "👎", "❤️", "😊", "😂", "🎉", "👏",
        "🙌", "🤔", "😅", "🙏", "💪", "🔥", "✨"
    ],
    "Objects": [
        "📝", "📚", "💻", "📱", "⌨️", "🖥️", "📸",
        "📁", "📂", "🗂️", "📊", "📈", "🔍", "🔎"
    ],
    "Communication": [
        "📧", "✉️", "💬", "🗨️", "🔔", "🔕", "📢",
        "🔊", "🔇", "📱", "☎️", "📞", "💭", "✍️"
    ]
}

def get_cache_dir() -> str:
    """Get the emoji cache directory path based on execution context."""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(__file__)
    
    cache_dir = os.path.join(base_path, 'cache', 'emojis')
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir

def cache_emojis(emoji_list: List[str], source: AlternativeCDNSource) -> Dict[str, bool]:
    """Cache a list of emojis and return success status for each."""
    results = {}
    total = len(emoji_list)
    
    for i, emoji in enumerate(emoji_list, 1):
        try:
            logger.info(f"Caching emoji {i}/{total}: {emoji}")
            result = source.get_emoji(emoji)
            success = result is not None
            results[emoji] = success
            if success:
                logger.info(f"Successfully cached: {emoji}")
            else:
                logger.warning(f"Failed to cache: {emoji}")
        except Exception as e:
            logger.error(f"Error caching {emoji}: {e}")
            results[emoji] = False
    
    return results

def save_cache_manifest(results: Dict[str, Dict[str, bool]], cache_dir: str):
    """Save a manifest of cached emojis with their status."""
    manifest_path = os.path.join(cache_dir, 'cache_manifest.json')
    try:
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        logger.info(f"Cache manifest saved to: {manifest_path}")
    except Exception as e:
        logger.error(f"Failed to save cache manifest: {e}")

def main():
    logger.info("Starting emoji pre-cache build process")
    
    # Initialize cache directory
    cache_dir = get_cache_dir()
    logger.info(f"Using cache directory: {cache_dir}")
    
    # Initialize emoji source
    source = AlternativeCDNSource(cache_dir=cache_dir)
    logger.info("Initialized AlternativeCDNSource")
    
    # Cache emojis and track results
    results = {}
    total_emojis = sum(len(emojis) for emojis in COMMON_EMOJIS.values())
    logger.info(f"Preparing to cache {total_emojis} emojis")
    
    for category, emojis in COMMON_EMOJIS.items():
        logger.info(f"\nProcessing category: {category}")
        results[category] = cache_emojis(emojis, source)
    
    # Save cache manifest
    save_cache_manifest(results, cache_dir)
    
    # Print summary
    success_count = sum(
        sum(1 for success in category_results.values() if success)
        for category_results in results.values()
    )
    
    logger.info("\n=== Cache Build Summary ===")
    logger.info(f"Total emojis processed: {total_emojis}")
    logger.info(f"Successfully cached: {success_count}")
    logger.info(f"Failed to cache: {total_emojis - success_count}")
    logger.info(f"Cache directory: {cache_dir}")
    
    # Return success status
    return success_count == total_emojis

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 