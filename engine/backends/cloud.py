"""
Cloud backend (paid tier).

Supports Anthropic Claude and OpenAI GPT models.
Uses the official Python SDKs for each provider.
"""

import os
import logging
from typing import AsyncIterator, Optional, Literal

logger = logging.getLogger(__name__)

ProviderKind = Literal["claude", "openai", "deepseek"]


class CloudBackend:
    """Async backend that talks to Claude (Anthropic) or GPT (OpenAI).

    Uses ANTHROPIC_API_KEY and OPENAI_API_KEY environment variables.
    """

    def __init__(
        self,
        provider: ProviderKind = "claude",
        model: Optional[str] = None,
        max_tokens: int = 4096,
    ):
        self.provider: ProviderKind = provider
        self.max_tokens = max_tokens

        if provider == "claude":
            self.model = model or os.environ.get("CLAUDE_MODEL") or "claude-sonnet-4-5"
            self._api_key = os.environ.get("ANTHROPIC_API_KEY")
            self._base_url: Optional[str] = None
            if not self._api_key:
                logger.warning("ANTHROPIC_API_KEY not set — Claude calls will fail.")
        elif provider == "openai":
            self.model = model or os.environ.get("OPENAI_MODEL") or "gpt-4o"
            self._api_key = os.environ.get("OPENAI_API_KEY")
            self._base_url: Optional[str] = None
            if not self._api_key:
                logger.warning("OPENAI_API_KEY not set — OpenAI calls will fail.")
        elif provider == "deepseek":
            self.model = model or os.environ.get("DEEPSEEK_MODEL") or "deepseek-chat"
            self._api_key = os.environ.get("DEEPSEEK_API_KEY")
            self._base_url = os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com/v1"
            if not self._api_key:
                logger.warning("DEEPSEEK_API_KEY not set — DeepSeek calls will fail.")
        else:
            raise ValueError(f"Unknown provider: {provider}. Use 'claude', 'openai', or 'deepseek'.")

        self._anthropic_client = None
        self._openai_client = None

    @property
    def api_key_present(self) -> bool:
        return bool(self._api_key)

    # ── Claude ──────────────────────────────────

    async def _claude_stream(self, prompt_text: str, system_prompt: str = "") -> AsyncIterator[str]:
        try:
            import anthropic
        except ImportError:
            raise RuntimeError(
                "anthropic package not installed. Run: pip install anthropic"
            )

        if self._anthropic_client is None:
            self._anthropic_client = anthropic.AsyncAnthropic(api_key=self._api_key)

        messages = [{"role": "user", "content": prompt_text}]
        kwargs: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": messages,
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        try:
            async with self._anthropic_client.messages.stream(**kwargs) as stream:
                async for event in stream:
                    if event.type == "content_block_delta":
                        text = event.delta.text
                        if text:
                            yield text
        except anthropic.AuthenticationError:
            raise RuntimeError("Invalid ANTHROPIC_API_KEY. Check your API key.")
        except anthropic.RateLimitError:
            raise RuntimeError("Anthropic rate limit exceeded. Try again later.")
        except Exception as exc:
            raise RuntimeError(f"Claude generation failed: {exc}") from exc

    async def _claude_full(self, prompt_text: str, system_prompt: str = "") -> str:
        try:
            import anthropic
        except ImportError:
            raise RuntimeError(
                "anthropic package not installed. Run: pip install anthropic"
            )

        if self._anthropic_client is None:
            self._anthropic_client = anthropic.AsyncAnthropic(api_key=self._api_key)

        messages = [{"role": "user", "content": prompt_text}]
        kwargs: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": messages,
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        try:
            response = await self._anthropic_client.messages.create(**kwargs)
            # response.content is a list of blocks; concatenate text blocks
            parts = []
            for block in response.content:
                if hasattr(block, "text"):
                    parts.append(block.text)
            return "".join(parts)
        except anthropic.AuthenticationError:
            raise RuntimeError("Invalid ANTHROPIC_API_KEY. Check your API key.")
        except anthropic.RateLimitError:
            raise RuntimeError("Anthropic rate limit exceeded. Try again later.")
        except Exception as exc:
            raise RuntimeError(f"Claude generation failed: {exc}") from exc

    # ── OpenAI ──────────────────────────────────

    async def _openai_stream(self, prompt_text: str, system_prompt: str = "") -> AsyncIterator[str]:
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise RuntimeError(
                "openai package not installed. Run: pip install openai"
            )

        if self._openai_client is None:
            kwargs: dict = {"api_key": self._api_key}
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._openai_client = AsyncOpenAI(**kwargs)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt_text})

        try:
            stream = await self._openai_client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=0.7,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield delta.content
        except Exception as exc:
            raise RuntimeError(f"OpenAI generation failed: {exc}") from exc

    async def _openai_full(self, prompt_text: str, system_prompt: str = "") -> str:
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise RuntimeError(
                "openai package not installed. Run: pip install openai"
            )

        if self._openai_client is None:
            kwargs: dict = {"api_key": self._api_key}
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._openai_client = AsyncOpenAI(**kwargs)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt_text})

        try:
            response = await self._openai_client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=0.7,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:
            raise RuntimeError(f"OpenAI generation failed: {exc}") from exc

    # ── Public API ──────────────────────────────

    async def generate(self, prompt_text: str, system_prompt: str = "") -> AsyncIterator[str]:
        """Generate text with streaming, yielding tokens."""
        if not self._api_key:
            raise RuntimeError(
                f"{self.provider.upper()} API key not set. "
                f"Set {'ANTHROPIC_API_KEY' if self.provider == 'claude' else 'OPENAI_API_KEY'} "
                f"environment variable."
            )

        if self.provider == "claude":
            async for token in self._claude_stream(prompt_text, system_prompt):
                yield token
        else:
            async for token in self._openai_stream(prompt_text, system_prompt):
                yield token

    async def generate_full(self, prompt_text: str, system_prompt: str = "") -> str:
        """Generate complete response (non-streaming)."""
        if not self._api_key:
            raise RuntimeError(
                f"{self.provider.upper()} API key not set. "
                f"Set {'ANTHROPIC_API_KEY' if self.provider == 'claude' else 'OPENAI_API_KEY'} "
                f"environment variable."
            )

        if self.provider == "claude":
            return await self._claude_full(prompt_text, system_prompt)
        else:
            return await self._openai_full(prompt_text, system_prompt)

    async def close(self) -> None:
        """Close any persistent connections."""
        if self._anthropic_client is not None:
            await self._anthropic_client.close()
        if self._openai_client is not None:
            await self._openai_client.close()
