# llmrouter.py
import os
import asyncio
import logging
from typing import List, Dict, Union, Optional
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
        if gemini_api_key:
            genai.configure(api_key=gemini_api_key)
            self.gemini_model = genai.GenerativeModel('gemini-pro')

    async def generate(
        self,
        model: str,
        messages: List[Dict[str, str]],
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
            logger.error(f"Error generating response: {e}")
            raise

    async def _generate_anthropic(
        self,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float,
        top_p: float,
        stop_sequences: Optional[List[str]] = None,
        image_data: Optional[Dict[str, str]] = None,
        system: Optional[str] = None
    ) -> str:
        """Generate response using Anthropic."""
        try:
            formatted_messages = [{"role": message["role"], "content": message["content"]} for message in messages]

            if image_data:
                formatted_messages[-1]["content"] = [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": image_data["media_type"],
                            "data": image_data["data"]
                        }
                    },
                    {"type": "text", "text": formatted_messages[-1]["content"]}
                ]

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
            logger.error(f"Anthropic API error: {e}")
            raise

    async def _generate_openai(
        self,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float,
        top_p: float,
        stop_sequences: Optional[List[str]] = None,
        image_data: Optional[Dict[str, str]] = None,
        system: Optional[str] = None
    ) -> str:
        """Generate response using OpenAI."""
        try:
            formatted_messages = [{"role": message["role"], "content": message["content"]} for message in messages]

            if system:
                formatted_messages.insert(0, {"role": "system", "content": system})

            if image_data:
                formatted_messages[-1]["content"] = [
                    {"type": "text", "text": formatted_messages[-1]["content"]},
                    {"type": "image_url", "image_url": image_data}
                ]

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
            logger.error(f"OpenAI API error: {e}")
            raise

    async def _generate_deepinfra(
        self,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float,
        top_p: float,
        stop_sequences: Optional[List[str]] = None,
        image_data: Optional[Dict[str, str]] = None,
        system: Optional[str] = None
    ) -> str:
        """Generate response using DeepInfra."""
        try:
            formatted_messages = [{"role": message["role"], "content": message["content"]} for message in messages]

            if system:
                formatted_messages.insert(0, {"role": "system", "content": system})

            if image_data:
                formatted_messages[-1]["content"] = [
                    {"type": "text", "text": formatted_messages[-1]["content"]},
                    {"type": "image_url", "image_url": image_data["data"]}
                ]

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
            logger.error(f"DeepInfra API error: {e}")
            raise

    async def _generate_gemini(
        self,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float,
        top_p: float,
        stop_sequences: Optional[List[str]] = None,
        image_data: Optional[Dict[str, str]] = None,
        system: Optional[str] = None
    ) -> str:
        """Generate response using Gemini."""
        try:
            # Convert messages to Gemini format
            gemini_messages = []
            for message in messages:
                if message["role"] == "system":
                    continue  # Gemini doesn't support system messages directly
                content = message["content"]
                if isinstance(content, list):
                    # Handle multimodal content
                    parts = []
                    for part in content:
                        if part["type"] == "text":
                            parts.append(part["text"])
                        elif part["type"] == "image_url":
                            # Handle image data if needed
                            pass
                    content = "\n".join(parts)
                gemini_messages.append({"role": message["role"], "parts": [content]})

            # Prepend system message to user's message if present
            if system and gemini_messages:
                user_message = gemini_messages[-1]["parts"][0]
                gemini_messages[-1]["parts"][0] = f"{system}\n\n{user_message}"

            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.gemini_model.generate_content(
                    gemini_messages[-1]["parts"][0],
                    generation_config=genai.types.GenerationConfig(
                        max_output_tokens=max_tokens,
                        temperature=temperature,
                        top_p=top_p,
                        stop_sequences=stop_sequences
                    )
                )
            )

            return response.text

        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            raise