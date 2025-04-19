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
from ocr import is_question_with_image, ocr_image, extract_question_from_ocr, extract_question_from_image_gemini
from question_processing import (get_answer_with_context, get_answer_without_context,
                               get_number_with_context, get_answer_with_image,
                               get_number_without_context, is_formatted_question)
from platform_interface import IconState
from license_manager import LicenseManager
import re

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
        self.screenshot = None  # Store the latest screenshot
        self.logger = logging.getLogger('ClipboardProcessor')
        self.search = None
        self.inverted_index = None
        self.documents = None  # Add documents attribute
        self.platform = None
        self.last_content = None
        self.processing = False
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
        required_attrs = ['llm_router']
        missing_attrs = [attr for attr in required_attrs if not hasattr(app, attr) or getattr(app, attr) is None]
        
        if missing_attrs:
            logger.debug(f"App missing required attributes: {missing_attrs}")
            return False

        # Check for document processing components but don't require them
        has_search = hasattr(app, 'search') and app.search is not None
        has_index = hasattr(app, 'inverted_index') and app.inverted_index is not None
        has_documents = hasattr(app, 'documents') and isinstance(app.documents, list)
        
        # Log component availability
        logger.debug(f"Document processing components available - Search: {has_search}, Index: {has_index}, Documents: {has_documents}")
        
        return True

    def _has_context_components(self) -> bool:
        """Check if all required components for context-based processing are available."""
        has_search = self.search is not None and callable(self.search)
        has_index = self.inverted_index is not None and hasattr(self.inverted_index, 'search')
        has_documents = isinstance(self.documents, list) and len(self.documents) > 0
        
        logger.debug(f"Context components check - Search: {has_search}, Index: {has_index}, Documents: {has_documents}")
        
        if not has_search:
            logger.debug("Search function not available or not callable")
        if not has_index:
            logger.debug("Inverted index not available or missing search attribute")
        if not has_documents:
            logger.debug("Documents not available or empty")
        
        return has_search and has_index and has_documents

    async def process_clipboard(self, app) -> None:
        """Process clipboard content with rate limiting and caching."""
        if self.processing:
            return  # Skip if already processing

        try:
            self.processing = True
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
                
                # Check if content is just a single word
                stripped_content = current_clipboard.strip()
                if len(stripped_content.split()) == 1:
                    app.update_icon(IconState.IDLE)
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
        finally:
            self.processing = False

    async def _process_question(self, text: str, app) -> tuple[bool, str]:
        """Process question with caching."""
        try:
            return await is_formatted_question(text, app.llm_router)
        except Exception as e:
            logger.error(f"Error processing question: {e}")
            return False, text

    async def process_screenshot(self, app) -> None:
        """Process screenshot with error handling and conditional pipeline."""
        if not self.screenshot:
            self.logger.warning("No screenshot data to process")
            return

        if self.processing:
            self.logger.warning("Screenshot processing already in progress")
            return

        self.processing = True
        try:
            app.update_icon(IconState.WORKING)
            self.logger.info("Starting screenshot processing")
            app.debug_info.append("Processing screenshot")

            # Check if it's a question with an image
            self.logger.info("Checking if screenshot contains a question with image")
            # Construct the data URL for image checking
            image_data_url = f"data:image/png;base64,{self.screenshot}"
            has_image = await is_question_with_image(image_data_url, app.llm_router)
            self.logger.info(f"Image detection result: {has_image}")

            if has_image:
                self.logger.info("Question with image detected")
                await self._process_image_question(app, self.screenshot)
            else:
                # Image contains mostly text
                self.logger.info("Screenshot detected as primarily text-based.")

                # === Reload settings to avoid potential Tkinter thread issues ===
                try:
                    app.settings.settings = app.settings._load_settings()
                    self.logger.debug("Reloaded settings from file before checking pipeline toggle.")
                except Exception as load_err:
                    self.logger.error(f"Error reloading settings: {load_err}. Proceeding with potentially stale settings.")
                # ================================================================

                # Check setting for which pipeline to use
                use_formula_pipeline = app.settings.get_setting('formula_screenshot_pipeline')
                self.logger.info(f"Formula support pipeline enabled: {use_formula_pipeline}")

                question = None
                if use_formula_pipeline:
                    self.logger.info("Using Gemini Vision pipeline for question extraction.")
                    try:
                        # Pass the base64 data directly if that's what the function expects
                        # Assuming image_data_url is correct based on extract_question_from_image_gemini signature
                        question = await extract_question_from_image_gemini(image_data_url, app.llm_router)
                    except Exception as gemini_e:
                        self.logger.error(f"Error during Gemini Vision question extraction: {gemini_e}", exc_info=True)
                        question = None # Fallback or handle error
                else:
                    self.logger.info("Using standard OCR + LLM pipeline for question extraction.")
                    try:
                        # Pass base64 string to the existing function
                        question = await extract_question_from_ocr(self.screenshot, app.llm_router)
                    except Exception as ocr_e:
                        self.logger.error(f"Error during OCR+LLM question extraction: {ocr_e}", exc_info=True)
                        question = None

                # Proceed with the extracted question if found
                if question:
                    self.logger.info("Question extracted successfully from screenshot text")
                    app.debug_info.append(f"Extracted question: {question[:200]}...")

                    # Split into non-empty lines for MCQ detection
                    lines = [line.strip() for line in question.split('\n') if line.strip()]

                    # Flexible MCQ detection logic (remains the same)
                    option_patterns = [
                        r'^[a-dA-D][\s\.\)]\s*\w+', # a) b) c) d) or A. B. C. D.
                        r'^[1-9][\s\.\)]\s*\w+',     # 1) 2) 3) or 1. 2. 3.
                        r'^\([a-dA-D]\)\s*\w+',      # (a) (b) (c) (d)
                        r'^\([1-9]\)\s*\w+'          # (1) (2) (3)
                    ]
                    option_count = sum(1 for line in lines[1:]
                                     if any(re.match(pattern, line) for pattern in option_patterns))
                    short_lines = sum(1 for line in lines[1:] if len(line) < 100)
                    is_mcq = (option_count >= 2) or (len(lines) > 2 and short_lines >= 2)

                    self.logger.info(f"MCQ detection - Option matches: {option_count}, Short lines: {short_lines}")

                    # Route to appropriate processing function
                    if is_mcq:
                        self.logger.info("Processing extracted text as MCQ question")
                        await self._process_mcq(app, question)
                    else:
                        self.logger.info("Processing extracted text as long-answer question")
                        await self._process_non_mcq(app, question)
                else:
                    self.logger.warning("No question could be extracted from screenshot using the selected pipeline.")
                    app.update_icon(IconState.ERROR)
                    await asyncio.sleep(2) # Show error state briefly
                    app.update_icon(IconState.IDLE)

            self.logger.info("Screenshot processing completed successfully")

        except Exception as e:
            self.logger.error(f"Error processing screenshot: {e}", exc_info=True)
            app.debug_info.append({
                "error": str(e),
                "error_type": type(e).__name__
            })
            app.update_icon(IconState.ERROR)
            app.debug_info.append(f"Screenshot processing failed: {str(e)}")
            await asyncio.sleep(2)  # Show error state briefly
            app.update_icon(IconState.IDLE)
            self.logger.info("Screenshot processing completed with errors")
        finally:
            self.processing = False
            self.screenshot = None  # Clear the screenshot after processing
            self.logger.debug("Screenshot processing resources cleaned up")

    def set_screenshot(self, screenshot_data: str) -> None:
        """Set screenshot data for processing."""
        self.screenshot = screenshot_data
        self.logger.debug("Screenshot data set for processing")

    async def _process_image_question(self, app, base64_image: str) -> None:
        """Process image-based question with error handling."""
        try:
            app.debug_info.append("Processing question with image")
            
            # Convert to the format expected by our updated llmrouter.py
            image_data = {
                "base64": base64_image,
                "mime_type": "image/png"
            }
            
            # Process directly with the updated get_answer_with_image function
            answer_text = await get_answer_with_image(
                "Answer the following question", app.llm_router, image_data
            )
            
            # Extract only the leading number/letter (e.g., "1.", "a", "C)", "(b)")
            extracted_answer = "Error" # Default value
            if answer_text:
                match = re.match(r"^\s*([\w\d]+[\.\)]?)", answer_text)
                if match:
                    extracted_answer = match.group(1).strip()
                else:
                    logger.warning(f"Could not extract MCQ answer from: '{answer_text}'")
            else:
                logger.warning("Received empty answer text from LLM for image question.")

            app.update_icon(IconState.MCQ_ANSWER, text=extracted_answer) # Use correct state and extracted text
            app.debug_info.append(f"MCQ answer with image: {extracted_answer}")

        except Exception as e:
            logger.error(f"Error processing image question: {e}", exc_info=True)
            app.update_icon(IconState.ERROR) # Use ERROR state on exception
            app.debug_info.append(f"Image question error: {str(e)}")

    async def _process_text_from_image(self, app, base64_image: str) -> None:
        """Process text extracted from image with error handling."""
        try:
            base64_image_url = f"data:image/png;base64,{base64_image}"
            
            # Try direct OCR first
            logger.info("Attempting direct OCR")
            extracted_text = await asyncio.get_event_loop().run_in_executor(
                None, ocr_image, base64_image
            )
            
            # If direct OCR fails or returns low-quality text, try OCR with LLM
            if not extracted_text or len(extracted_text.strip().split()) < 5:
                logger.info("Direct OCR failed or returned low-quality text, trying OCR with LLM")
                extracted_text = await asyncio.get_event_loop().run_in_executor(
                    None, extract_question_from_ocr, base64_image, app.llm_router
                )
            
            if not extracted_text:
                raise ValueError("Failed to extract text from image")
            
            logger.info(f"Successfully extracted text from image: {extracted_text[:200]}...")
            app.debug_info.append(f"Extracted Text: {extracted_text}")
            
            # Process the extracted text
            is_mcq, clipboard = await self._process_question(extracted_text, app)
            app.debug_info.append(f"MCQ detected: {is_mcq}")
            
            if is_mcq:
                await self._process_mcq(app, clipboard)
            else:
                await self._process_non_mcq(app, clipboard)

        except Exception as e:
            logger.error(f"Error processing text from image: {e}")
            app.update_icon(IconState.ERROR)
            app.debug_info.append(f"Screenshot processing error: {str(e)}")

    async def _process_mcq(self, app, text: str) -> None:
        """Process MCQ with error handling and caching."""
        try:
            logger.info(f"Starting MCQ processing with text length: {len(text)}")
            logger.info(f"MCQ text content: {text[:500]}...")
            app.update_icon(IconState.WORKING)
            
            # Check for context components
            has_context = self._has_context_components()
            logger.info(f"Context-based processing available: {has_context}")
            
            # Try with context first if components are available
            answer_number = None
            if has_context:
                logger.info("Attempting to get answer with context")
                try:
                    # Use local components instead of app components
                    answer_number = await asyncio.wait_for(
                        get_number_with_context(
                            text, app.llm_router, self.search, self.inverted_index, self.documents
                        ),
                        timeout=30.0
                    )
                    logger.info(f"Answer with context result: {answer_number}")
                except asyncio.TimeoutError:
                    logger.error("Context-based answer timed out")
                    answer_number = None
                except Exception as context_error:
                    logger.error(f"Error getting context-based answer: {context_error}")
                    answer_number = None
            else:
                logger.info("Skipping context-based answer - components not available")
                logger.debug(f"Search type: {type(self.search)}")
                logger.debug(f"Index type: {type(self.inverted_index)}")
                logger.debug(f"Documents length: {len(self.documents) if isinstance(self.documents, list) else 'N/A'}")

            # Fallback to without context if needed
            if answer_number is None:
                logger.info("Attempting to get answer without context")
                try:
                    answer_number = await asyncio.wait_for(
                        get_number_without_context(text, app.llm_router),
                        timeout=30.0
                    )
                    logger.info(f"Answer without context result: {answer_number}")
                except asyncio.TimeoutError:
                    logger.error("Non-context answer timed out")
                    answer_number = None
                except Exception as no_context_error:
                    logger.error(f"Error getting non-context answer: {no_context_error}")
                    answer_number = None
            
            if answer_number is not None:
                logger.info(f"Processing successful, updating UI with answer: {answer_number}")
                app.update_icon(IconState.MCQ_ANSWER, text=answer_number)
                app.debug_info.append(f"MCQ answer: {answer_number}")
                app.last_clipboard = text
            else:
                logger.error("Failed to get MCQ answer")
                app.update_icon(IconState.ERROR)
                await asyncio.sleep(2)
                app.update_icon(IconState.IDLE)

        except Exception as e:
            logger.error(f"Unexpected error in _process_mcq: {e}", exc_info=True)
            app.update_icon(IconState.ERROR)
            await asyncio.sleep(2)
            app.update_icon(IconState.IDLE)

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

    def set_platform(self, platform):
        """Set the platform interface for UI updates."""
        self.platform = platform
        self.logger.debug("Platform interface set")