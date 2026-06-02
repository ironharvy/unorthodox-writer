"""
Shared pytest fixtures for the engine test suite.

Network-dependent fixtures auto-skip when the resource is unavailable:
  * the Ollama fixtures skip if the server can't be reached;
  * the DeepSeek fixture skips if ``DEEPSEEK_API_KEY`` is unset.

Models on the Ollama server (192.168.1.20:11434):
  * qwen3:latest        — fast 8B, default for tests
  * qwen3.6:27b         — 27B, quality reference
  * nemotron-3-nano:4b  — fast 4B, 256K context
"""

import os
import sys

import httpx
import pytest
import pytest_asyncio

# Make the repo root importable so ``import engine`` works under pytest.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from engine.backends.ollama import OllamaBackend  # noqa: E402
from engine.backends.cloud import CloudBackend  # noqa: E402

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://192.168.1.20:11434")

SMALL_MODEL = "qwen3:latest"
LARGE_MODEL = "qwen3.6:27b"
NEMOTRON_MODEL = "nemotron-3-nano:4b"


def _ollama_reachable(url: str) -> bool:
    try:
        resp = httpx.get(f"{url}/api/tags", timeout=3.0)
        return resp.status_code == 200
    except Exception:
        return False


# Evaluated once per session — cheap network probe.
OLLAMA_AVAILABLE = _ollama_reachable(OLLAMA_URL)

# Reusable skip marker for tests that talk to Ollama directly (not via a fixture).
requires_ollama = pytest.mark.skipif(
    not OLLAMA_AVAILABLE, reason=f"Ollama not reachable at {OLLAMA_URL}"
)


def _available_models() -> set[str]:
    if not OLLAMA_AVAILABLE:
        return set()
    try:
        resp = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=3.0)
        return {m["name"] for m in resp.json().get("models", [])}
    except Exception:
        return set()


AVAILABLE_MODELS = _available_models()


async def _make_backend(model: str) -> OllamaBackend:
    backend = OllamaBackend(base_url=OLLAMA_URL, model=model)
    if not await backend.health_check():
        await backend.close()
        pytest.skip(f"Ollama not reachable at {OLLAMA_URL}")
    if AVAILABLE_MODELS and model not in AVAILABLE_MODELS:
        await backend.close()
        pytest.skip(f"model {model} not present on server")
    return backend


@pytest_asyncio.fixture
async def ollama_backend():
    """Fast 8B model — the default for most tests."""
    backend = await _make_backend(SMALL_MODEL)
    yield backend
    await backend.close()


@pytest_asyncio.fixture
async def ollama_backend_large():
    """27B quality model."""
    backend = await _make_backend(LARGE_MODEL)
    yield backend
    await backend.close()


@pytest_asyncio.fixture
async def nemotron_backend():
    """Fast 4B model with a 256K context window."""
    backend = await _make_backend(NEMOTRON_MODEL)
    yield backend
    await backend.close()


@pytest_asyncio.fixture
async def deepseek_backend():
    """Paid-tier DeepSeek backend; skips when no API key is configured."""
    backend = CloudBackend(provider="deepseek")
    if not backend.api_key_present:
        pytest.skip("DEEPSEEK_API_KEY not set")
    yield backend
    await backend.close()
