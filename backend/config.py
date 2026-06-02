"""Application configuration. Override with environment variables."""

import os


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./unorthodox_writer.db")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://192.168.1.20:11434")

# Ollama model selection. OLLAMA_MODEL drives short stories (fast); the optional
# OLLAMA_MODEL_NOVEL overrides the model used for free-tier novel runs.
#   - qwen3:latest        (8B)   — fast, default for short stories / tests
#   - qwen3.6:27b         (27B)  — highest quality, slower
#   - nemotron-3-nano:4b  (4B)   — fastest, 256K context (long-range coherence)
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:latest")
OLLAMA_MODEL_NOVEL = os.getenv("OLLAMA_MODEL_NOVEL", OLLAMA_MODEL)

# CORS — allow Vite dev server
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

# Tier limits
# Bumped from 500 → 2000 so free (Ollama) users can exercise the novel pipeline.
FREE_MAX_WORDS = int(os.getenv("FREE_MAX_WORDS", "2000"))
FREE_MAX_DAILY_STORIES = 5
FREE_MAX_SAVED_STORIES = 3

# When True, free-tier requests above FREE_NOVEL_THRESHOLD words are routed
# through the multi-phase NovelPipeline (driven by Ollama) instead of the
# single-pass StoryPipeline.
FREE_NOVEL_ENABLED = os.getenv("FREE_NOVEL_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
FREE_NOVEL_THRESHOLD = int(os.getenv("FREE_NOVEL_THRESHOLD", "500"))
