"""
Ollama backend (free tier).

Connects to a local Ollama instance via its HTTP API.
Uses the ``/api/chat`` endpoint with streaming JSON lines.

Why ``/api/chat`` (not ``/api/generate``):
  * Modern instruction-tuned models (qwen3, nemotron) are trained on chat
    templates and follow instructions more reliably through proper role
    messages than through a flat ``prompt`` string.
  * "Thinking" models (qwen3, nemotron) return their chain-of-thought in a
    separate ``message.thinking`` field, leaving ``message.content`` clean.
    The flat ``/api/generate`` endpoint would interleave ``<think>`` blocks
    into the prose. We collect only ``content`` so reasoning never leaks into
    the story.

Context window:
  Ollama defaults to ``num_ctx=2048``, which silently truncates the long
  prompts the drafting/critique phases build. We set ``num_ctx`` explicitly
  (default 8192, configurable) so prompts are not clipped.
"""

import json
import os
import logging
from typing import AsyncIterator, Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_URL = "http://192.168.1.20:11434"
DEFAULT_MODEL = "qwen3.6:27b"
DEFAULT_NUM_CTX = 8192


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


class OllamaBackend:
    """Async backend that talks to a local Ollama instance via ``/api/chat``."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 600.0,
        num_ctx: Optional[int] = None,
        num_predict: Optional[int] = None,
        temperature: float = 0.7,
        top_p: float = 0.9,
        think: Optional[bool] = None,
    ):
        """
        Args:
            base_url: Ollama server URL (env: ``OLLAMA_URL``).
            model: model tag, e.g. ``qwen3:latest`` (env: ``OLLAMA_MODEL``).
            timeout: per-request timeout in seconds.
            num_ctx: context window size in tokens (env: ``OLLAMA_NUM_CTX``,
                default 8192). Must be large enough to hold the prompt + reply.
            num_predict: max tokens to generate (env: ``OLLAMA_NUM_PREDICT``).
                ``None`` (default) leaves Ollama's own default in place — the
                chat endpoint generates until EOS, so the model finishes its
                sentence rather than being clipped mid-thought. Set this only to
                impose an explicit cap; give it enough headroom that the prompt's
                "finish the current sentence cleanly" guard can take effect (a
                ~250-word story needs ~400+ tokens), or stories will truncate.
            temperature: sampling temperature.
            top_p: nucleus sampling cutoff.
            think: enable the model's chain-of-thought. Defaults to ``False``
                (env: ``OLLAMA_THINK``) — thinking is correctly separated into
                its own field, but it adds large latency, and the multi-call
                novel pipeline makes that prohibitive. Only ``content`` is ever
                returned to the caller regardless of this flag.
        """
        self.base_url = (base_url or os.environ.get("OLLAMA_URL") or DEFAULT_OLLAMA_URL).rstrip("/")
        self.model = model or os.environ.get("OLLAMA_MODEL") or DEFAULT_MODEL
        self.timeout = timeout
        env_ctx = os.environ.get("OLLAMA_NUM_CTX")
        self.num_ctx = num_ctx if num_ctx is not None else (int(env_ctx) if env_ctx else DEFAULT_NUM_CTX)
        self.temperature = temperature
        self.top_p = top_p
        self.think = think if think is not None else _env_flag("OLLAMA_THINK", False)
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

    async def list_models(self) -> list[str]:
        """Return the model tags available on the server."""
        client = await self._get_client()
        resp = await client.get(f"{self.base_url}/api/tags")
        resp.raise_for_status()
        return [m["name"] for m in resp.json().get("models", [])]

    def _build_payload(
        self, prompt_text: str, system_prompt: str, stream: bool, json_mode: bool = False,
    ) -> dict:
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt_text})
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "think": self.think,
            "options": {
                "temperature": self.temperature,
                "top_p": self.top_p,
                "num_ctx": self.num_ctx,
            },
        }
        if json_mode:
            # Constrain the model to emit a single valid JSON object. This makes
            # the novel pipeline's bible/critique parsing far more reliable.
            payload["format"] = "json"
        return payload

    async def _generate_stream(
        self, prompt_text: str, system_prompt: str = "", json_mode: bool = False,
    ) -> AsyncIterator[str]:
        """Yield ``content`` tokens from a streaming ``/api/chat`` request.

        ``message.thinking`` tokens are intentionally dropped so the model's
        chain-of-thought never leaks into the generated prose.
        """
        client = await self._get_client()
        payload = self._build_payload(prompt_text, system_prompt, stream=True, json_mode=json_mode)

        try:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/chat",
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
                    if chunk.get("error"):
                        raise RuntimeError(f"Ollama error: {chunk['error']}")
                    token = (chunk.get("message") or {}).get("content", "")
                    if token:
                        yield token
                    if chunk.get("done"):
                        break
        except httpx.ConnectError as exc:
            raise RuntimeError(
                f"Cannot connect to Ollama at {self.base_url}. Is it running?"
            ) from exc
        except httpx.TimeoutException as exc:
            raise RuntimeError(f"Ollama request timed out after {self.timeout}s") from exc

    async def generate(self, prompt_text: str, system_prompt: str = "") -> AsyncIterator[str]:
        """Generate text from a prompt, yielding content tokens as they arrive."""
        async for token in self._generate_stream(prompt_text, system_prompt):
            yield token

    async def generate_full(
        self, prompt_text: str, system_prompt: str = "", json_mode: bool = False,
    ) -> str:
        """Generate complete response (non-streaming, collects all content tokens).

        When ``json_mode`` is True the model is constrained to emit valid JSON
        (Ollama ``format: "json"``). The NovelPipeline detects this kwarg and
        uses it for the bible/critique calls.
        """
        parts: list[str] = []
        async for token in self._generate_stream(prompt_text, system_prompt, json_mode=json_mode):
            parts.append(token)
        return "".join(parts)
