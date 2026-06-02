"""
Backend tests — OllamaBackend (live) and CloudBackend (config + optional live).

The Ollama tests hit the real server (auto-skip if unreachable). They use the
fast 8B model and tiny prompts to stay quick.
"""

import os

import pytest

from engine.backends.ollama import OllamaBackend, DEFAULT_NUM_CTX
from engine.backends.cloud import CloudBackend
from .conftest import OLLAMA_URL, SMALL_MODEL, LARGE_MODEL


# ── OllamaBackend: configuration (no network) ───────────────


def test_ollama_defaults():
    b = OllamaBackend()
    assert b.num_ctx == DEFAULT_NUM_CTX == 8192
    assert b.think is False  # thinking off by default for speed
    assert b.base_url.startswith("http")


def test_ollama_num_ctx_override():
    assert OllamaBackend(num_ctx=16384).num_ctx == 16384


def test_ollama_env_num_ctx(monkeypatch):
    monkeypatch.setenv("OLLAMA_NUM_CTX", "4096")
    assert OllamaBackend().num_ctx == 4096


def test_ollama_payload_uses_chat_shape():
    b = OllamaBackend(model="qwen3:latest", num_ctx=8192)
    payload = b._build_payload("hello", "be terse", stream=True)
    assert payload["model"] == "qwen3:latest"
    assert payload["options"]["num_ctx"] == 8192
    assert payload["messages"][0] == {"role": "system", "content": "be terse"}
    assert payload["messages"][1] == {"role": "user", "content": "hello"}
    assert payload["stream"] is True


def test_ollama_payload_no_system():
    payload = OllamaBackend()._build_payload("hi", "", stream=False)
    assert len(payload["messages"]) == 1
    assert payload["messages"][0]["role"] == "user"


# ── OllamaBackend: live ─────────────────────────────────────


async def test_ollama_health_check(ollama_backend):
    assert await ollama_backend.health_check() is True


async def test_ollama_list_models(ollama_backend):
    models = await ollama_backend.list_models()
    assert isinstance(models, list) and models
    assert any("qwen3" in m for m in models)


async def test_ollama_generate(ollama_backend):
    text = await ollama_backend.generate_full(
        "Write about 50 words describing a thunderstorm at sea. Prose only.",
        "You are a concise fiction writer.",
    )
    assert isinstance(text, str)
    words = text.split()
    assert len(words) >= 20, f"expected real prose, got {len(words)} words"
    # No reasoning tokens leaked into the content.
    assert "<think>" not in text.lower()


async def test_ollama_streaming(ollama_backend):
    tokens = []
    async for tok in ollama_backend.generate("List three sea creatures, comma separated.", ""):
        tokens.append(tok)
    assert len(tokens) >= 1
    joined = "".join(tokens)
    assert joined.strip(), "stream produced empty output"
    assert "<think>" not in joined.lower()


async def test_ollama_model_switch():
    """qwen3:latest and qwen3.6:27b should both respond (short prompts)."""
    out = {}
    for model in (SMALL_MODEL, LARGE_MODEL):
        b = OllamaBackend(base_url=OLLAMA_URL, model=model)
        if not await b.health_check():
            await b.close()
            pytest.skip("Ollama not reachable")
        try:
            models = await b.list_models()
            if model not in models:
                pytest.skip(f"{model} not present")
            text = await b.generate_full("Reply with exactly one word: ready", "")
            out[model] = text.strip()
        finally:
            await b.close()
    assert out[SMALL_MODEL]
    assert out[LARGE_MODEL]


async def test_ollama_num_ctx_applied(ollama_backend):
    """A custom num_ctx should not break generation."""
    b = OllamaBackend(model=SMALL_MODEL, num_ctx=4096)
    try:
        text = await b.generate_full("Say hello in one word.", "")
        assert text.strip()
    finally:
        await b.close()


# ── CloudBackend: configuration ─────────────────────────────


def test_cloud_provider_defaults():
    claude = CloudBackend(provider="claude")
    assert claude.provider == "claude"
    assert "claude" in claude.model.lower()

    deepseek = CloudBackend(provider="deepseek")
    assert deepseek.provider == "deepseek"
    assert deepseek._base_url and "deepseek" in deepseek._base_url


def test_cloud_unknown_provider_raises():
    with pytest.raises(ValueError):
        CloudBackend(provider="not-a-provider")  # type: ignore[arg-type]


def test_cloud_api_key_present_reflects_env(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert CloudBackend(provider="openai").api_key_present is False
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert CloudBackend(provider="openai").api_key_present is True


async def test_cloud_generate_without_key_raises(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    backend = CloudBackend(provider="openai")
    with pytest.raises(RuntimeError):
        await backend.generate_full("hello")


async def test_deepseek_generate_live(deepseek_backend):
    """Only runs when DEEPSEEK_API_KEY is set (otherwise the fixture skips)."""
    text = await deepseek_backend.generate_full("Reply with exactly one word: ok", "")
    assert text.strip()
