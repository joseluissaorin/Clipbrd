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
from platform_interface import IconState
from license_manager import LicenseManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure specific loggers
logging.getLogger('PIL').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('keyring').setLevel(logging.WARNING)
logging.getLogger('license_manager').setLevel(logging.INFO)

class ClipboardProcessor:
    DEFAULT_POLLING_INTERVAL = 1  # Default polling interval in seconds
    
    def __init__(self, cache_size: int = 1000):
        self.clipboard_cache = deque(maxlen=cache_size)
        self.processing_lock = asyncio.Lock()
        self.last_process_time = 0
        self.rate_limit_delay = 0.1  # 100ms between processes
        self._setup_caches()
        self._initial_content = None
        self.last_processed_content = None
        # Initialize immediately in constructor
        self.initialize()
        logger.info("ClipboardProcessor initialized")

    def _test_clipboard_access(self) -> bool:
        """Test clipboard access without affecting monitoring."""
        try:
            # Save current clipboard content
            original_content = clipman.paste()
            
            # Perform test
            test_content = "clipbrd_test_content_123"
            clipman.copy(test_content)
            result = clipman.paste() == test_content
            
            # Restore original content or clear if None
            if original_content:
                clipman.copy(original_content)
            else:
                clipman.copy('')
            
            return result
        except Exception as e:
            logger.error(f"Failed to test clipboard access: {e}")
            return False

    def initialize(self) -> bool:
        """Initialize the clipboard processor."""
        try:
            # Initialize clipman
            clipman.init()
            
            # Test clipboard access
            if not self._test_clipboard_access():
                logger.error("Failed to verify clipboard access")
                return False
                
            # Store initial clipboard state and set as last processed
            self._initial_content = clipman.paste()
            self.last_processed_content = self._initial_content
            self.clipboard_cache.append(self.cached_normalize(self._initial_content or ''))
            logger.info("Clipboard processor initialized with initial content")
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
            # Don't return empty strings
            return content if content and content.strip() else None
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

    def _validate_app_requirements(self, app) -> bool:
        """Validate that the app has all required attributes for processing."""
        required_attrs = ['llm_router', 'search', 'inverted_index', 'documents']
        missing_attrs = [attr for attr in required_attrs if not hasattr(app, attr) or getattr(app, attr) is None]
        
        if missing_attrs:
            logger.debug(f"App missing required attributes: {missing_attrs}")
            return False
        return True

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
                
                # Check if content is the same as last processed or initial
                if (current_clipboard == self.last_processed_content or 
                    current_clipboard == self._initial_content):
                    return
                
                normalized_clipboard = self.cached_normalize(current_clipboard)
                
                # Cache check
                if normalized_clipboard in self.clipboard_cache:
                    app.debug_info.append("Content found in cache")
                    return
                
                # Validation
                if not self.cached_validate(normalized_clipboard):
                    app.debug_info.append("Content failed validation")
                    return

                # Validate app has required attributes before processing
                if not self._validate_app_requirements(app):
                    app.debug_info.append("App not ready for processing")
                    return

                # Log new content detected
                logger.info("New clipboard content detected")

                # Update cache and state
                self.clipboard_cache.append(normalized_clipboard)
                self.last_processed_content = current_clipboard
                app.last_clipboard = current_clipboard
                app.debug_info.append(f"Clipboard content: {current_clipboard}")

                # Process content
                app.update_icon(IconState.WORKING)
                logger.info("Processing clipboard content")
                is_mcq, clipboard = await self._process_question(current_clipboard, app)
                app.debug_info.append(f"MCQ detected: {is_mcq}")

                if is_mcq:
                    logger.info("Processing MCQ question")
                    await self._process_mcq(app, clipboard)
                else:
                    logger.info("Processing non-MCQ question")
                    await self._process_non_mcq(app, current_clipboard)

                self.last_process_time = time.time()

            # Use constant polling interval
            await asyncio.sleep(self.DEFAULT_POLLING_INTERVAL)

        except Exception as e:
            logger.error(f"Error processing clipboard: {e}")
            app.update_icon(IconState.ERROR)

    async def _process_question(self, text: str, app) -> tuple[bool, str]:
        """Process question with caching."""
        try:
            return await is_formatted_question(text, app.llm_router)
        except Exception as e:
            logger.error(f"Error processing question: {e}")
            return False, text

    async def process_screenshot(self, app) -> None:
        """Process screenshot with error handling."""
        try:
            if app.screenshot is None:
                app.update_icon(IconState.IDLE)
                return

            logger.info("Processing screenshot")
            app.update_icon(IconState.SCREENSHOT)
            base64_image = app.screenshot

            await self._process_text_from_image(app, base64_image)
            app.screenshot = None

        except Exception as e:
            logger.error(f"Error processing screenshot: {e}")
            app.update_icon(IconState.ERROR)

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
            logger.info(f"Starting MCQ processing with text length: {len(text)}")
            app.update_icon(IconState.WORKING)  # Start with WORKING state
            # Try with context first
            answer_number = None
            if app.search and app.inverted_index and app.documents:
                logger.info("Attempting to get answer with context")
                answer_number = await asyncio.get_event_loop().run_in_executor(
                    None, get_number_with_context,
                    text, app.llm_router, app.search, app.inverted_index, app.documents
                )
                logger.info(f"Answer with context result: {answer_number}")
            else:
                logger.info("Skipping context-based answer (missing components)")
            
            # Fallback to without context
            if answer_number is None:
                logger.info("Attempting to get answer without context")
                answer_number = await get_number_without_context(text, app.llm_router)
                logger.info(f"Answer without context result: {answer_number}")
            
            if answer_number is not None:
                app.update_icon(IconState.MCQ_ANSWER, str(answer_number))  # Pass the answer as text
                app.debug_info.append(f"MCQ answer: {answer_number}")
                app.last_clipboard = text
                logger.info(f"MCQ processed successfully, answer: {answer_number}")
            else:
                app.update_icon(IconState.ERROR)
                logger.error("Failed to get MCQ answer: answer_number is None")

        except Exception as e:
            logger.error(f"Error processing MCQ: {str(e)}", exc_info=True)
            logger.error(f"MCQ text that caused error: {text[:200]}...")  # Log first 200 chars of problematic text
            app.update_icon(IconState.ERROR)

    async def _process_non_mcq(self, app, text: str) -> None:
        """Process non-MCQ with error handling and caching."""
        try:
            app.update_icon(IconState.WORKING)
            # Try with context first
            logger.info("Attempting to get answer with context")
            answer = await get_answer_with_context(text, app.llm_router, app.search, app.inverted_index, app.documents)
            logger.info(f"Answer with context result: {'Found' if answer else 'None'}")
            
            # Fallback to without context
            if answer is None:
                logger.info("Attempting to get answer without context")
                answer = await get_answer_without_context(text, app.llm_router)
                logger.info(f"Answer without context received: {answer[:100] if answer else 'None'}...")  # Log first 100 chars
            
            if answer:
                # Store the answer in app and update last processed content
                app.question_clipboard = answer
                self.last_processed_content = answer  # Update before copying to clipboard
                self.clipboard_cache.append(self.cached_normalize(answer))  # Add to cache
                
                # Now copy to clipboard
                clipman.copy(answer)
                
                app.update_icon(IconState.SUCCESS)
                app.debug_info.append(f"Answer: {answer}")
                logger.info("Non-MCQ processed successfully")
            else:
                app.update_icon(IconState.ERROR)
                logger.error("Failed to get answer: answer is None")

        except Exception as e:
            logger.error(f"Error processing non-MCQ: {e}", exc_info=True)
            app.update_icon(IconState.ERROR)