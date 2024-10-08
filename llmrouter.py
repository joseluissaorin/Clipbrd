# llmrouter.py
import os
from typing import List, Dict, Union
from anthropic import Anthropic
from openai import OpenAI

class LLMRouter:
    def __init__(self, anthropic_api_key: str, openai_api_key: str, deepinfra_api_key: str):
        self.anthropic_client = Anthropic(api_key=anthropic_api_key)
        self.openai_client = OpenAI(api_key=openai_api_key)
        self.deepinfra_client = OpenAI(api_key=deepinfra_api_key, base_url='https://api.deepinfra.com/v1/openai')

    def generate(self, model: str, messages: List[Dict[str, str]], max_tokens: int, temperature: float, top_p: float, stop_sequences: List[str] = None, image_data: Dict[str, str] = None, system: str = None) -> Union[str, Dict[str, str]]:
        if model.startswith("claude"):
            return self._generate_anthropic(model, messages, max_tokens, temperature, top_p, stop_sequences, image_data, system)
        elif model.startswith("gpt"):
            return self._generate_openai(model, messages, max_tokens, temperature, top_p, stop_sequences, image_data, system)
        else:
            return self._generate_deepinfra(model, messages, max_tokens, temperature, top_p, stop_sequences, image_data, system)

    def _generate_anthropic(self, model: str, messages: List[Dict[str, str]], max_tokens: int, temperature: float, top_p: float, stop_sequences: List[str] = None, image_data: Dict[str, str] = None, system: str = None) -> Union[str, Dict[str, str]]:
        formatted_messages = [{"role": message["role"], "content": message["content"]} for message in messages]

        if image_data:
            formatted_messages[-1]["content"] = [
                {"type": "image", "source": {"type": "base64", "media_type": image_data["media_type"], "data": image_data["data"]}},
                {"type": "text", "text": formatted_messages[-1]["content"]}
            ]

        response = self.anthropic_client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stop_sequences=stop_sequences,
            messages=formatted_messages,
            system=system
        )

        return response.content[0].text

    def _generate_openai(self, model: str, messages: List[Dict[str, str]], max_tokens: int, temperature: float, top_p: float, stop_sequences: List[str] = None, image_data: Dict[str, str] = None, system: str = None) -> Union[str, Dict[str, str]]:
        formatted_messages = [{"role": message["role"], "content": message["content"]} for message in messages]

        if system:
            formatted_messages.insert(0, {"role": "system", "content": system})

        if image_data:
            formatted_messages[-1]["content"] = [
                {"type": "text", "text": formatted_messages[-1]["content"]},
                {"type": "image_url", "image_url": image_data}
            ]

        response = self.openai_client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            messages=formatted_messages
        )

        return response.choices[0].message.content

    def _generate_deepinfra(self, model: str, messages: List[Dict[str, str]], max_tokens: int, temperature: float, top_p: float, stop_sequences: List[str] = None, image_data: Dict[str, str] = None, system: str = None) -> Union[str, Dict[str, str]]:
        formatted_messages = [{"role": message["role"], "content": message["content"]} for message in messages]

        if system:
            formatted_messages.insert(0, {"role": "system", "content": system})

        if image_data:
            formatted_messages[-1]["content"] = [
                {"type": "text", "text": formatted_messages[-1]["content"]},
                {"type": "image_url", "image_url": image_data["data"]}
            ]

        response = self.deepinfra_client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stop=stop_sequences,
            messages=formatted_messages
        )

        return response.choices[0].message.content