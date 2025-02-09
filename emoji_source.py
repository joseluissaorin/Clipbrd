import os
import logging
import requests
import json
from io import BytesIO
from typing import Optional, Dict, Set, Tuple
from urllib.parse import quote
from pilmoji.source import BaseSource
from functools import lru_cache
from pathlib import Path
from PIL import Image

logger = logging.getLogger(__name__)

class AlternativeCDNSource(BaseSource):
    """Custom emoji source using the alternative CDN with fallback chain."""
    
    BASE_URL = "https://emoji-cdn.mqrio.dev"
    
    def __init__(self, cache_dir: Optional[str] = None):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 Clipbrd Emoji Client'
        })
        
        # Fallback chain configuration
        self.styles = [
            'twitter',    # Primary style
            'openmoji',      # Fast fallback
            'emojidex'       # Reliable backup
        ]
        
        # Setup caching
        self.cache_dir = cache_dir
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)
        
        # Initialize error tracking
        self.error_counts: Dict[str, int] = {style: 0 for style in self.styles}
        self.max_errors = 3  # Switch to fallback after 3 errors
        
        # Verify cache on initialization
        if cache_dir:
            self.verify_cache()
        
        logger.info(f"Initialized AlternativeCDNSource with {len(self.styles)} fallback styles")

    def verify_cache(self) -> Tuple[bool, Dict[str, Set[str]]]:
        """Verify the integrity of the emoji cache and return status with details."""
        if not self.cache_dir:
            return False, {}

        manifest_path = os.path.join(self.cache_dir, 'cache_manifest.json')
        if not os.path.exists(manifest_path):
            logger.warning("Cache manifest not found")
            return False, {}

        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load cache manifest: {e}")
            return False, {}

        verification_results: Dict[str, Set[str]] = {
            'missing': set(),
            'corrupted': set(),
            'verified': set()
        }

        # Verify each emoji in the manifest
        for category, emoji_results in manifest.items():
            for emoji, was_cached in emoji_results.items():
                if not was_cached:
                    continue

                cache_path = self._get_cache_path(emoji)
                if not cache_path.exists():
                    verification_results['missing'].add(emoji)
                    continue

                try:
                    # Try to open and verify the image
                    with Image.open(cache_path) as img:
                        img.verify()
                    verification_results['verified'].add(emoji)
                except Exception as e:
                    logger.error(f"Corrupted cache file for emoji {emoji}: {e}")
                    verification_results['corrupted'].add(emoji)
                    try:
                        # Remove corrupted file
                        cache_path.unlink()
                    except Exception as del_e:
                        logger.error(f"Failed to delete corrupted cache file: {del_e}")

        # Log verification results
        total_verified = len(verification_results['verified'])
        total_issues = len(verification_results['missing']) + len(verification_results['corrupted'])
        
        if total_issues > 0:
            logger.warning(f"Cache verification found issues: {total_issues} problems, {total_verified} verified")
            logger.debug(f"Missing emojis: {verification_results['missing']}")
            logger.debug(f"Corrupted emojis: {verification_results['corrupted']}")
        else:
            logger.info(f"Cache verification successful: {total_verified} emojis verified")

        return total_issues == 0, verification_results

    def repair_cache(self, verification_results: Dict[str, Set[str]]) -> bool:
        """Attempt to repair cache issues by re-downloading problematic emojis."""
        if not self.cache_dir:
            return False

        problem_emojis = verification_results['missing'].union(verification_results['corrupted'])
        if not problem_emojis:
            return True

        logger.info(f"Attempting to repair {len(problem_emojis)} emoji cache issues")
        success_count = 0

        for emoji in problem_emojis:
            try:
                result = self._fetch_and_cache_emoji(emoji)
                if result:
                    success_count += 1
                    logger.info(f"Successfully repaired cache for emoji: {emoji}")
                else:
                    logger.warning(f"Failed to repair cache for emoji: {emoji}")
            except Exception as e:
                logger.error(f"Error repairing cache for emoji {emoji}: {e}")

        repair_success = success_count == len(problem_emojis)
        logger.info(f"Cache repair completed: {success_count}/{len(problem_emojis)} fixed")
        return repair_success

    def _fetch_and_cache_emoji(self, emoji: str) -> bool:
        """Fetch an emoji and cache it, returning success status."""
        for style in self.styles:
            try:
                data = self._fetch_emoji(emoji, style)
                if data:
                    if self.cache_dir:
                        self._save_to_cache(emoji, data)
                    return True
            except Exception as e:
                logger.error(f"Failed to fetch emoji {emoji} with style {style}: {e}")
        return False

    @lru_cache(maxsize=100)
    def get_emoji(self, emoji: str, /) -> Optional[BytesIO]:
        """Get emoji image with fallback support and caching."""
        logger.debug(f"Requesting emoji: {emoji}")
        
        # Try cache first
        if self.cache_dir:
            cached = self._get_from_cache(emoji)
            if cached:
                return cached

        # Try each style in the fallback chain
        for style in self.styles:
            if self.error_counts[style] >= self.max_errors:
                logger.warning(f"Skipping {style} due to error count: {self.error_counts[style]}")
                continue

            try:
                result = self._fetch_emoji(emoji, style)
                if result:
                    # Reset error count on success
                    self.error_counts[style] = 0
                    # Cache successful result
                    if self.cache_dir:
                        self._save_to_cache(emoji, result)
                    return BytesIO(result)
            except Exception as e:
                logger.error(f"Error fetching emoji with {style}: {e}")
                self.error_counts[style] += 1

        logger.error(f"All styles failed for emoji: {emoji}")
        return None

    def _fetch_emoji(self, emoji: str, style: str) -> Optional[bytes]:
        """Fetch emoji from CDN with specific style."""
        url = f"{self.BASE_URL}/{quote(emoji)}?style={style}"
        try:
            response = self.session.get(url)
            if response.ok:
                return response.content
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
        return None

    def _get_cache_path(self, emoji: str) -> Path:
        """Get the cache file path for an emoji."""
        if not self.cache_dir:
            return None
        # Use emoji code points as filename
        filename = "-".join(f"{ord(c):x}" for c in emoji) + ".png"
        return Path(self.cache_dir) / filename

    def _get_from_cache(self, emoji: str) -> Optional[BytesIO]:
        """Try to get emoji from cache."""
        if not self.cache_dir:
            return None
            
        cache_path = self._get_cache_path(emoji)
        if cache_path and cache_path.exists():
            try:
                with open(cache_path, 'rb') as f:
                    return BytesIO(f.read())
            except Exception as e:
                logger.error(f"Failed to read from cache: {e}")
        return None

    def _save_to_cache(self, emoji: str, data: bytes) -> None:
        """Save emoji to cache."""
        if not self.cache_dir:
            return
            
        cache_path = self._get_cache_path(emoji)
        if cache_path:
            try:
                with open(cache_path, 'wb') as f:
                    f.write(data)
            except Exception as e:
                logger.error(f"Failed to write to cache: {e}")

    def get_discord_emoji(self, id: int, /) -> Optional[BytesIO]:
        """Not implemented as not needed for our use case."""
        return None

    def clear_cache(self) -> None:
        """Clear the emoji cache directory."""
        if self.cache_dir:
            try:
                for file in Path(self.cache_dir).glob("*.png"):
                    file.unlink()
                logger.info("Cache cleared successfully")
            except Exception as e:
                logger.error(f"Failed to clear cache: {e}")

    def __repr__(self) -> str:
        return f"<AlternativeCDNSource styles={self.styles} cache_enabled={bool(self.cache_dir)}>" 