"""AI Engine — unified interface for LLM providers (OpenAI, Anthropic, Ollama)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator


@dataclass
class AIMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class AIResponse:
    content: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    raw: Any = None


class AIEngine:
    """
    Unified AI generation interface.

    Supports OpenAI-compatible APIs out of the box.

    Usage::

        ai = AIEngine(
            provider="openai",
            model="gpt-4o-mini",
            api_key="sk-...",
        )
        response = await ai.generate("Explain quantum computing")
        print(response.content)
    """

    PROVIDERS: dict[str, str] = {
        "openai": "https://api.openai.com/v1/chat/completions",
        "anthropic": "https://api.anthropic.com/v1/messages",
        "ollama": "http://localhost:11434/api/chat",
        "groq": "https://api.groq.com/openai/v1/chat/completions",
    }

    def __init__(
        self,
        provider: str = "openai",
        model: str = "gpt-4o-mini",
        api_key: str = "",
        base_url: str | None = None,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> None:
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.base_url = base_url or self.PROVIDERS.get(provider, "")
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def generate(
        self,
        prompt: str,
        *,
        messages: list[AIMessage] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AIResponse:
        """Generate a completion from the configured LLM."""
        msgs = []
        if self.system_prompt:
            msgs.append({"role": "system", "content": self.system_prompt})
        if messages:
            msgs.extend({"role": m.role, "content": m.content} for m in messages)
        msgs.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": msgs,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
            **kwargs,
        }
        if self.provider == "anthropic":
            return await self._call_anthropic(payload)
        return await self._call_openai_compatible(payload)

    async def generate_stream(
        self,
        prompt: str,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream tokens from the LLM (requires httpx)."""
        try:
            import httpx
        except ImportError:
            raise ImportError("Install httpx for streaming: pip install httpx")

        msgs = []
        if self.system_prompt:
            msgs.append({"role": "system", "content": self.system_prompt})
        msgs.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": msgs,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
            **kwargs,
        }

        headers = self._build_headers()
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST", self.base_url, json=payload, headers=headers, timeout=120
            ) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: ") and line != "data: [DONE]":
                        chunk = json.loads(line[6:])
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content

    async def _call_openai_compatible(self, payload: dict) -> AIResponse:
        try:
            import httpx
        except ImportError:
            raise ImportError("Install httpx: pip install httpx")

        headers = self._build_headers()
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.base_url, json=payload, headers=headers, timeout=120)
            resp.raise_for_status()
            data = resp.json()

        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        usage = data.get("usage", {})
        return AIResponse(content=content, model=self.model, usage=usage, raw=data)

    async def _call_anthropic(self, payload: dict) -> AIResponse:
        try:
            import httpx
        except ImportError:
            raise ImportError("Install httpx: pip install httpx")

        # Anthropic uses a different format
        system = next(
            (m["content"] for m in payload.get("messages", []) if m["role"] == "system"), ""
        )
        messages = [m for m in payload.get("messages", []) if m["role"] != "system"]
        anthropic_payload = {
            "model": payload["model"],
            "messages": messages,
            "max_tokens": payload.get("max_tokens", 2048),
            "system": system,
        }

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.base_url, json=anthropic_payload, headers=headers, timeout=120)
            resp.raise_for_status()
            data = resp.json()

        content = data.get("content", [{}])[0].get("text", "")
        usage = data.get("usage", {})
        return AIResponse(content=content, model=self.model, usage=usage, raw=data)

    def _build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers
