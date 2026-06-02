"""
Ollama backend (free tier).

Connects to a local Ollama instance via its HTTP API.
Uses the /api/generate endpoint with streaming JSON lines.
"""

import json
import os
import logging
from typing import AsyncIterator, Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_URL = "http://192.168.1.20:11434"
DEFAULT_MODEL = "qwen3.6:27b"


class OllamaBackend:
    """Async backend that talks to a local Ollama instance."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 120.0,
    ):
        self.base_url = (base_url or os.environ.get("OLLAMA_URL") or DEFAULT_OLLAMA_URL).rstrip("/")
        self.model = model or os.environ.get("OLLAMA_MODEL") or DEFAULT_MODEL
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(self.timeout))
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def health_check(self) -> bool:
        """Check if the Ollama server is reachable."""
        client = await self._get_client()
        try:
            resp = await client.get(f"{self.base_url}/api/tags")
            return resp.status_code == 200
        except Exception as exc:
            logger.warning(f"Ollama health check failed: {exc}")
            return False

    async def _generate_stream(self, prompt_text: str, system_prompt: str = "") -> AsyncIterator[str]:
        """Yield tokens from a streaming Ollama generate request."""
        client = await self._get_client()
        payload = {
            "model": self.model,
            "prompt": prompt_text,
            "stream": True,
            "options": {
                "temperature": 0.7,
                "top_p": 0.9,
            },
        }
        if system_prompt:
            payload["system"] = system_prompt

        try:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/generate",
                json=payload,
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    raise RuntimeError(
                        f"Ollama returned {response.status_code}: {body.decode()[:500]}"
                    )
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if chunk.get("done"):
                        break
                    token = chunk.get("response", "")
                    if token:
                        yield token
        except httpx.ConnectError as exc:
            raise RuntimeError(
                f"Cannot connect to Ollama at {self.base_url}. Is it running?"
            ) from exc
        except httpx.TimeoutException as exc:
            raise RuntimeError(f"Ollama request timed out after {self.timeout}s") from exc

    async def generate(self, prompt_text: str, system_prompt: str = "") -> AsyncIterator[str]:
        """Generate text from a prompt, yielding tokens as they arrive."""
        async for token in self._generate_stream(prompt_text, system_prompt):
            yield token

    async def generate_full(self, prompt_text: str, system_prompt: str = "") -> str:
        """Generate complete response (non-streaming, collects all tokens)."""
        parts: list[str] = []
        async for token in self._generate_stream(prompt_text, system_prompt):
            parts.append(token)
        return "".join(parts)
