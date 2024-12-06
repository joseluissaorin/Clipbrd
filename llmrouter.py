# llmrouter.py
import os
import time
import asyncio
import logging
from typing import List, Dict, Union, Optional, Any
from dataclasses import dataclass
from collections import deque
from functools import lru_cache
from anthropic import Anthropic
from openai import OpenAI

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class CacheEntry:
    """Cache entry for LLM responses."""
    response: str
    timestamp: float
    model: str

class LLMRouter:
    def __init__(
        self,
        anthropic_api_key: str,
        openai_api_key: str,
        deepinfra_api_key: str,
        cache_size: int = 1000,
        cache_ttl: int = 3600  # 1 hour cache TTL
    ):
        self.anthropic_client = Anthropic(api_key=anthropic_api_key)
        self.openai_client = OpenAI(api_key=openai_api_key)
        self.deepinfra_client = OpenAI(
            api_key=deepinfra_api_key,
            base_url='https://api.deepinfra.com/v1/openai'
        )
        
        # Initialize caches and rate limiting
        self.response_cache = deque(maxlen=cache_size)
        self.cache_ttl = cache_ttl
        self.cache_dict = {}
        self.rate_limits = {
            "anthropic": {"tokens": 100000, "requests": 50, "window": 60},  # per minute
            "openai": {"tokens": 80000, "requests": 40, "window": 60},
            "deepinfra": {"tokens": 60000, "requests": 30, "window": 60}
        }
        self.request_timestamps = {
            "anthropic": deque(maxlen=50),
            "openai": deque(maxlen=40),
            "deepinfra": deque(maxlen=30)
        }
        self.token_usage = {
            "anthropic": deque(maxlen=50),
            "openai": deque(maxlen=40),
            "deepinfra": deque(maxlen=30)
        }
        self._setup_caches()

    def _setup_caches(self):
        """Setup LRU caches for various operations."""
        self.cached_format_messages = lru_cache(maxsize=1000)(self._format_messages)
        self.cached_hash_request = lru_cache(maxsize=1000)(self._hash_request)

    def _hash_request(
        self,
        model: str,
        messages: tuple,  # Convert list to tuple for hashing
        max_tokens: int,
        temperature: float,
        top_p: float
    ) -> str:
        """Create a unique hash for a request."""
        return f"{model}_{hash(messages)}_{max_tokens}_{temperature}_{top_p}"

    def _format_messages(self, messages: List[Dict[str, str]], system: Optional[str] = None) -> List[Dict[str, str]]:
        """Format messages with caching."""
        formatted = [{"role": msg["role"], "content": msg["content"]} for msg in messages]
        if system:
            formatted.insert(0, {"role": "system", "content": system})
        return formatted

    async def _check_rate_limit(self, provider: str) -> None:
        """Check and enforce rate limits."""
        current_time = time.time()
        window_start = current_time - self.rate_limits[provider]["window"]
        
        # Clean up old timestamps
        while (self.request_timestamps[provider] and 
               self.request_timestamps[provider][0] < window_start):
            self.request_timestamps[provider].popleft()
            self.token_usage[provider].popleft()
        
        # Check limits
        if len(self.request_timestamps[provider]) >= self.rate_limits[provider]["requests"]:
            sleep_time = self.request_timestamps[provider][0] - window_start
            await asyncio.sleep(sleep_time)
        
        total_tokens = sum(self.token_usage[provider])
        if total_tokens >= self.rate_limits[provider]["tokens"]:
            sleep_time = self.request_timestamps[provider][0] - window_start
            await asyncio.sleep(sleep_time)

    def _update_rate_limit(self, provider: str, tokens: int) -> None:
        """Update rate limit tracking."""
        self.request_timestamps[provider].append(time.time())
        self.token_usage[provider].append(tokens)

    def _get_cached_response(self, cache_key: str) -> Optional[str]:
        """Get cached response if valid."""
        if cache_key in self.cache_dict:
            entry = self.cache_dict[cache_key]
            if time.time() - entry.timestamp < self.cache_ttl:
                return entry.response
            del self.cache_dict[cache_key]
        return None

    def _cache_response(self, cache_key: str, response: str, model: str) -> None:
        """Cache a response."""
        entry = CacheEntry(response=response, timestamp=time.time(), model=model)
        self.cache_dict[cache_key] = entry

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
    ) -> Union[str, Dict[str, str]]:
        """Generate response with caching and rate limiting."""
        try:
            # Check cache first
            cache_key = self._hash_request(
                model,
                tuple(tuple(sorted(m.items())) for m in messages),
                max_tokens,
                temperature,
                top_p
            )
            
            cached_response = self._get_cached_response(cache_key)
            if cached_response:
                return cached_response

            # Route to appropriate provider
            if model.startswith("claude"):
                response = await self._generate_anthropic(
                    model, messages, max_tokens, temperature,
                    top_p, stop_sequences, image_data, system
                )
            elif model.startswith("gpt"):
                response = await self._generate_openai(
                    model, messages, max_tokens, temperature,
                    top_p, stop_sequences, image_data, system
                )
            else:
                response = await self._generate_deepinfra(
                    model, messages, max_tokens, temperature,
                    top_p, stop_sequences, image_data, system
                )

            # Cache successful response
            self._cache_response(cache_key, response, model)
            return response

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
        """Generate response using Anthropic with rate limiting."""
        await self._check_rate_limit("anthropic")
        
        try:
            formatted_messages = self.cached_format_messages(messages)
            
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

            self._update_rate_limit("anthropic", response.usage.output_tokens)
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
        """Generate response using OpenAI with rate limiting."""
        await self._check_rate_limit("openai")
        
        try:
            formatted_messages = self.cached_format_messages(messages, system)

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

            self._update_rate_limit("openai", response.usage.total_tokens)
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
        """Generate response using DeepInfra with rate limiting."""
        await self._check_rate_limit("deepinfra")
        
        try:
            formatted_messages = self.cached_format_messages(messages, system)

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

            self._update_rate_limit("deepinfra", response.usage.total_tokens)
            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"DeepInfra API error: {e}")
            raise