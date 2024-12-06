# clipboard_processing.py
import base64
import io
import asyncio
import logging
import time
from typing import Optional, Dict, Any, Tuple
from functools import lru_cache
from collections import deque
import clipman
from ocr import is_question_with_image, ocr_image, extract_question_from_ocr
from question_processing import (get_answer_with_context, get_answer_without_context,
                               get_number_with_context, get_answer_with_image,
                               get_number_without_context, is_formatted_question)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ClipboardProcessor:
    def __init__(self, cache_size: int = 1000):
        self.clipboard_cache = deque(maxlen=cache_size)
        self.processing_lock = asyncio.Lock()
        self.last_process_time = 0
        self.rate_limit_delay = 0.1  # 100ms between processes
        self._setup_caches()

    async def initialize(self) -> bool:
        """Initialize the clipboard processor."""
        try:
            # Initialize clipman
            clipman.init()
            
            # Verify clipboard access
            clipman.copy("test")
            test_content = clipman.paste()
            if test_content != "test":
                logger.error("Failed to verify clipboard access")
                return False
            return True
        except Exception as e:
            logger.error(f"Failed to initialize clipboard processor: {e}")
            return False

    def cleanup(self):
        """Cleanup resources."""
        try:
            pass
        except Exception as e:
            logger.error(f"Error during clipboard cleanup: {e}")

    async def get_content(self) -> Optional[str]:
        """Get content from clipboard."""
        try:
            content = clipman.paste()
            if isinstance(content, bytes):
                try:
                    return content.decode('utf-8')
                except UnicodeDecodeError:
                    return None
            return content
        except Exception as e:
            logger.error(f"Error getting clipboard content: {e}")
            return None

    def _setup_caches(self):
        """Setup LRU caches for various operations."""
        self.cached_normalize = lru_cache(maxsize=1000)(self._normalize_text)
        self.cached_validate = lru_cache(maxsize=1000)(self._validate_clipboard)

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize clipboard text."""
        return ' '.join(text.split())

    @staticmethod
    def _validate_clipboard(text: str) -> bool:
        """Validate clipboard content."""
        return bool(text and len(text.split()) > 1)

    async def process_clipboard(self, app) -> None:
        """Process clipboard content with rate limiting and caching."""
        try:
            # Rate limiting
            current_time = time.time()
            time_since_last = current_time - self.last_process_time
            if time_since_last < self.rate_limit_delay:
                await asyncio.sleep(self.rate_limit_delay - time_since_last)

            async with self.processing_lock:
                current_clipboard = clipman.paste()
                
                # Quick validation checks
                if not current_clipboard:
                    return
                
                normalized_clipboard = self.cached_normalize(current_clipboard)
                
                # Cache check
                if normalized_clipboard in self.clipboard_cache:
                    return
                
                # Validation
                if not self.cached_validate(normalized_clipboard):
                    app.update_icon("Clipbrd")
                    return

                # Update cache and state
                self.clipboard_cache.append(normalized_clipboard)
                app.last_clipboard = current_clipboard
                app.debug_info.append(f"Clipboard content: {current_clipboard}")

                # Process content
                is_mcq, clipboard = await self._process_question(current_clipboard, app)
                app.debug_info.append(f"MCQ detected: {is_mcq}")

                app.update_icon("Clipbrd: Working.")
                if is_mcq:
                    await self._process_mcq(app, clipboard)
                else:
                    await self._process_non_mcq(app, current_clipboard)

                self.last_process_time = time.time()

        except Exception as e:
            logger.error(f"Error processing clipboard: {e}")
            app.update_icon("Clipbrd: Error")

    async def _process_question(self, text: str, app) -> Tuple[bool, str]:
        """Process question with caching."""
        try:
            return await asyncio.get_event_loop().run_in_executor(
                None, is_formatted_question, text, app.llm_router
            )
        except Exception as e:
            logger.error(f"Error processing question: {e}")
            return False, text

    async def process_screenshot(self, app) -> None:
        """Process screenshot with error handling."""
        try:
            if app.screenshot is None:
                return

            logger.info("Processing screenshot")
            base64_image = app.screenshot

            await self._process_text_from_image(app, base64_image)
            app.screenshot = None

        except Exception as e:
            logger.error(f"Error processing screenshot: {e}")
            app.update_icon("Clipbrd: Error")

    async def _process_image_question(self, app, base64_image: str) -> None:
        """Process image-based question with error handling."""
        try:
            app.debug_info.append("Processing question with image")
            image_data = {
                "url": f"data:image/png;base64,{base64_image}",
                "detail": "high"
            }
            
            answer_number = await asyncio.get_event_loop().run_in_executor(
                None, get_answer_with_image,
                "Answer the following question", app.llm_router, image_data
            )
            
            app.update_icon(f"Clipbrd: {answer_number}")
            app.debug_info.append(f"MCQ answer with image: {answer_number}")

        except Exception as e:
            logger.error(f"Error processing image question: {e}")
            app.update_icon("Clipbrd: Error")

    async def _process_text_from_image(self, app, base64_image: str) -> None:
        """Process text extracted from image with error handling."""
        try:
            base64_image_url = f"data:image/png;base64,{base64_image}"
            
            # Try primary OCR
            extracted_text = await asyncio.get_event_loop().run_in_executor(
                None, extract_question_from_ocr, base64_image, app.llm_router
            )
            
            # Fallback OCR
            if not extracted_text:
                extracted_text = await asyncio.get_event_loop().run_in_executor(
                    None, ocr_image, base64_image
                )
            
            if not extracted_text:
                raise ValueError("Failed to extract text from image")
            
            app.debug_info.append(f"Extracted Text: {extracted_text}")
            is_mcq, clipboard = await self._process_question(extracted_text, app)
            
            app.debug_info.append(f"MCQ detected: {is_mcq}")
            if is_mcq:
                await self._process_mcq(app, clipboard)
            else:
                await self._process_non_mcq(app, clipboard)

        except Exception as e:
            logger.error(f"Error processing text from image: {e}")
            app.update_icon("Clipbrd: Error")

    async def _process_mcq(self, app, text: str) -> None:
        """Process MCQ with error handling and caching."""
        try:
            # Try with context first
            answer_number = await asyncio.get_event_loop().run_in_executor(
                None, get_number_with_context,
                text, app.llm_router, app.search, app.inverted_index, app.documents
            )
            
            # Fallback to without context
            if answer_number is None:
                answer_number = await asyncio.get_event_loop().run_in_executor(
                    None, get_number_without_context,
                    text, app.llm_router
                )
            
            app.update_icon(f"Clipbrd: {answer_number}")
            app.debug_info.append(f"MCQ answer: {answer_number}")
            app.last_clipboard = text

        except Exception as e:
            logger.error(f"Error processing MCQ: {e}")
            app.update_icon("Clipbrd: Error")

    async def _process_non_mcq(self, app, text: str) -> None:
        """Process non-MCQ with error handling and caching."""
        try:
            # Try with context first
            answer = await asyncio.get_event_loop().run_in_executor(
                None, get_answer_with_context,
                text, app.llm_router, app.search, app.inverted_index, app.documents
            )
            
            # Fallback to without context
            if answer is None:
                answer = await asyncio.get_event_loop().run_in_executor(
                    None, get_answer_without_context,
                    text, app.llm_router
                )
            
            app.question_clipboard = answer
            clipman.copy(answer)
            app.update_icon("Clipbrd: Done.")
            app.debug_info.append(f"Answer: {answer}")

        except Exception as e:
            logger.error(f"Error processing non-MCQ: {e}")
            app.update_icon("Clipbrd: Error")