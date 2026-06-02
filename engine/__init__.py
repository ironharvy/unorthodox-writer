"""
Unorthodox Writer — Story Engine

Model-agnostic story generation pipelines with multi-stage processing.
Supports local Ollama (free tier) and Claude/GPT/DeepSeek APIs (paid tier).

  - StoryPipeline  — single-pass expand → outline → draft → polish, for short
                     stories (<2000 words).
  - NovelPipeline  — multi-phase, canon-tracked novel generation (bible →
                     chapter-by-chapter drafting → critique → revision), for
                     paid-tier novel-length work.

Usage:
    from engine import StoryPipeline

    pipeline = StoryPipeline(tier="free")
    async for event in pipeline.generate(prompt="A detective in space..."):
        print(event)
"""

from engine.pipeline import StoryPipeline
from engine.novel import NovelPipeline, StoryBible, ChapterBeat
from engine.backends import OllamaBackend, CloudBackend

__all__ = [
    "StoryPipeline",
    "NovelPipeline",
    "StoryBible",
    "ChapterBeat",
    "OllamaBackend",
    "CloudBackend",
]
__version__ = "0.2.0"
