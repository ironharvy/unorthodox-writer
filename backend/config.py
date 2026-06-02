"""Application configuration. Override with environment variables."""

import os


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./unorthodox_writer.db")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://192.168.1.20:11434")

# CORS — allow Vite dev server
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

# Tier limits
FREE_MAX_WORDS = 500
FREE_MAX_DAILY_STORIES = 5
FREE_MAX_SAVED_STORIES = 3
