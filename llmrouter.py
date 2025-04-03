# llmrouter.py
import os
import asyncio
import logging
import base64
from typing import List, Dict, Union, Optional, Any
from anthropic import Anthropic
from openai import OpenAI
import google.generativeai as genai

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LLMRouter:
    def __init__(
        self,
        anthropic_api_key: str,
        openai_api_key: str,
        deepinfra_api_key: str,
        gemini_api_key: str = None,
    ):
        self.anthropic_client = Anthropic(api_key=anthropic_api_key)
        self.openai_client = OpenAI(api_key=openai_api_key)
        self.deepinfra_client = OpenAI(
            api_key=deepinfra_api_key,
            base_url='https://api.deepinfra.com/v1/openai'
        )
        
        # Initialize Gemini model with proper error handling
        self.gemini_model = None
        if gemini_api_key:
            try:
                # Configure the API key
                genai.configure(api_key=gemini_api_key)
                
                # Initialize with a model for vision capabilities
                self.gemini_model = genai.GenerativeModel('gemini-2.0-flash')
                logger.info("Successfully initialized Gemini 2.0 Flash model")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini model: {e}")
                self.gemini_model = None
        else:
            logger.warning("No Gemini API key provided, Gemini model will be unavailable")

    async def generate(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        max_tokens: int,
        temperature: float,
        top_p: float,
        stop_sequences: Optional[List[str]] = None,
        image_data: Optional[Dict[str, str]] = None,
        system: Optional[str] = None
    ) -> str:
        """Generate response using the appropriate model."""
        try:
            if model.startswith("claude"):
                return await self._generate_anthropic(
                    model, messages, max_tokens, temperature,
                    top_p, stop_sequences, image_data, system
                )
            elif model.startswith("gpt"):
                return await self._generate_openai(
                    model, messages, max_tokens, temperature,
                    top_p, stop_sequences, image_data, system
                )
            elif model.startswith("gemini"):
                if not hasattr(self, 'gemini_model') or self.gemini_model is None:
                    logger.error("Gemini model not available, cannot process request.")
                    raise RuntimeError("Gemini model required but not available.")

                return await self._generate_gemini(
                    model, messages, max_tokens, temperature,
                    top_p, stop_sequences, image_data, system
                )
            else:
                return await self._generate_deepinfra(
                    model, messages, max_tokens, temperature,
                    top_p, stop_sequences, image_data, system
                )
        except Exception as e:
            logger.error(f"Error generating response: {e}", exc_info=True)
            raise

    async def _generate_anthropic(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        max_tokens: int,
        temperature: float,
        top_p: float,
        stop_sequences: Optional[List[str]] = None,
        image_data: Optional[Dict[str, str]] = None,
        system: Optional[str] = None
    ) -> str:
        """Generate response using Anthropic."""
        try:
            formatted_messages = []
            for msg in messages:
                content = msg['content']
                if isinstance(content, list):
                    text_content = " ".join(part['text'] for part in content if part['type'] == 'text')
                else:
                    text_content = content
                formatted_messages.append({"role": msg["role"], "content": text_content})

            if image_data and 'base64' in image_data and 'mime_type' in image_data:
                if formatted_messages:
                    last_content = formatted_messages[-1]["content"]
                    if not isinstance(last_content, list):
                        last_content = [{"type": "text", "text": last_content}]

                    last_content.insert(0, {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": image_data["mime_type"],
                            "data": image_data["base64"]
                        }
                    })
                    formatted_messages[-1]["content"] = last_content
                else:
                    logger.warning("Cannot add image data to empty message list for Anthropic.")

            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.anthropic_client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                    stop_sequences=stop_sequences,
                    messages=formatted_messages,
                    system=system
                )
            )

            return response.content[0].text

        except Exception as e:
            logger.error(f"Anthropic API error: {e}", exc_info=True)
            raise

    async def _generate_openai(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        max_tokens: int,
        temperature: float,
        top_p: float,
        stop_sequences: Optional[List[str]] = None,
        image_data: Optional[Dict[str, str]] = None,
        system: Optional[str] = None
    ) -> str:
        """Generate response using OpenAI."""
        try:
            formatted_messages = []
            for msg in messages:
                content = msg['content']
                if isinstance(content, list):
                    text_content = " ".join(part['text'] for part in content if part['type'] == 'text')
                else:
                    text_content = content
                formatted_messages.append({"role": msg["role"], "content": text_content})

            if system:
                formatted_messages.insert(0, {"role": "system", "content": system})

            if image_data and 'base64' in image_data and 'mime_type' in image_data:
                if formatted_messages:
                    last_content_text = formatted_messages[-1]["content"]
                    formatted_messages[-1]["content"] = [
                        {"type": "text", "text": last_content_text},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{image_data['mime_type']};base64,{image_data['base64']}",
                                "detail": "high"
                            }
                        }
                    ]
                else:
                    logger.warning("Cannot add image data to empty message list for OpenAI.")

            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.openai_client.chat.completions.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                    messages=formatted_messages
                )
            )

            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"OpenAI API error: {e}", exc_info=True)
            raise

    async def _generate_deepinfra(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        max_tokens: int,
        temperature: float,
        top_p: float,
        stop_sequences: Optional[List[str]] = None,
        image_data: Optional[Dict[str, str]] = None,
        system: Optional[str] = None
    ) -> str:
        """Generate response using DeepInfra (assuming OpenAI compatibility)."""
        try:
            formatted_messages = []
            for msg in messages:
                content = msg['content']
                if isinstance(content, list):
                    text_content = " ".join(part['text'] for part in content if part['type'] == 'text')
                else:
                    text_content = content
                formatted_messages.append({"role": msg["role"], "content": text_content})

            if system:
                formatted_messages.insert(0, {"role": "system", "content": system})

            if image_data and 'base64' in image_data and 'mime_type' in image_data:
                if formatted_messages:
                    last_content_text = formatted_messages[-1]["content"]
                    formatted_messages[-1]["content"] = [
                        {"type": "text", "text": last_content_text},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{image_data['mime_type']};base64,{image_data['base64']}",
                                "detail": "high"
                            }
                        }
                    ]
                else:
                    logger.warning("Cannot add image data to empty message list for DeepInfra.")

            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.deepinfra_client.chat.completions.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                    stop=stop_sequences,
                    messages=formatted_messages
                )
            )

            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"DeepInfra API error: {e}", exc_info=True)
            raise

    async def _generate_gemini(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        max_tokens: int,
        temperature: float,
        top_p: float,
        stop_sequences: Optional[List[str]] = None,
        image_data: Optional[Dict[str, str]] = None,
        system: Optional[str] = None
    ) -> str:
        """Generate response using Gemini, handling multimodal input."""
        try:
            if not self.gemini_model:
                raise RuntimeError("Gemini model is not initialized.")

            # Prepare the content
            content_parts = []

            # Add system prompt if provided
            system_prefix = f"{system}\n\n" if system else ""

            # Get the text from messages
            text_prompt = ""
            if messages:
                last_message = messages[-1]
                if last_message["role"] == "user":
                    content = last_message["content"]
                    if isinstance(content, list):
                        text_prompt = " ".join(part['text'] for part in content if part['type'] == 'text')
                    elif isinstance(content, str):
                        text_prompt = content
                    else:
                        logger.warning(f"Unsupported content type in Gemini message: {type(content)}")
                else:
                    logger.warning("Last message for Gemini is not from user role.")
                    if isinstance(messages[-1]['content'], str):
                        text_prompt = messages[-1]['content']
            
            # Combine system prompt and text
            full_text_prompt = f"{system_prefix}{text_prompt}"
            
            # Create the content parts list
            if full_text_prompt:
                # Add text part
                content_parts.append({"text": full_text_prompt})

            # Add image if provided
            if image_data and 'base64' in image_data and 'mime_type' in image_data:
                try:
                    # Create the image part
                    image_bytes = base64.b64decode(image_data['base64'])
                    image_part = {
                        "inline_data": {
                            "mime_type": image_data['mime_type'],
                            "data": base64.b64encode(image_bytes).decode('utf-8')
                        }
                    }
                    content_parts.append(image_part)
                    logger.debug(f"Appended image part ({image_data['mime_type']}) to Gemini contents.")
                except Exception as img_e:
                    logger.error(f"Failed to decode or add image part for Gemini: {img_e}", exc_info=True)
                    raise ValueError(f"Invalid image data provided for Gemini: {img_e}") from img_e
            
            # Check if we have content to send
            if not content_parts:
                logger.error("Cannot make Gemini request with empty contents.")
                return ""

            # Create generation config
            generation_config = {
                "max_output_tokens": max_tokens,
                "temperature": temperature,
                "top_p": top_p
            }
            
            if stop_sequences:
                generation_config["stop_sequences"] = stop_sequences

            # Generate content
            logger.debug(f"Generating content with Gemini using {len(content_parts)} parts.")
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.gemini_model.generate_content(
                    content_parts,
                    generation_config=generation_config
                )
            )

            # Handle response
            if hasattr(response, 'text'):
                return response.text
            elif hasattr(response, 'parts') and response.parts:
                return response.parts[0].text
            elif hasattr(response, 'candidates') and response.candidates:
                return response.candidates[0].content.parts[0].text
            else:
                # Check for blocking
                if hasattr(response, 'prompt_feedback') and response.prompt_feedback and hasattr(response.prompt_feedback, 'block_reason'):
                    logger.warning(f"Gemini request blocked due to: {response.prompt_feedback.block_reason}")
                    return f"[Request blocked by safety filter: {response.prompt_feedback.block_reason}]"
                else:
                    logger.warning("Gemini response has no usable content.")
                    return "[Empty response from model]"

        except Exception as e:
            logger.error(f"Gemini API error: {e}", exc_info=True)
            raise