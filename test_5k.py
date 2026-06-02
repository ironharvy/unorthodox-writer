"""Direct engine test: 5000 words with scaled sections."""
import asyncio, os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine.pipeline import StoryPipeline

async def main():
    pipeline = StoryPipeline(
        tier="paid",
        cloud_provider="deepseek",
        cloud_model="deepseek-chat",
        cloud_max_tokens=4096,
    )
    
    prompt = "A street musician in Prague discovers his violin can play notes that make people relive their happiest memory"
    
    print(f"Generating 5000-word story...\n")
    start = time.time()
    
    sections_seen = 0
    chunks = 0
    async for event in pipeline.generate(
        prompt=prompt, genre="fantasy", style="descriptive",
        max_words=5000, pov="first_person",
    ):
        etype = event.get("type", "?")
        if etype == "progress":
            msg = event.get("message", "")
            if "sections" in msg.lower():
                sections_seen = int(event.get("data", {}).get("section_count", 0))
            print(f"  [{event.get('stage','?')}] {msg}")
        elif etype == "chunk":
            chunks += 1
        elif etype == "complete":
            elapsed = time.time() - start
            wc = event.get("word_count", 0)
            print(f"\nDone in {elapsed:.0f}s — {wc} words, {sections_seen} sections")
            print(f"Title: {event.get('title', '?')}")
            # Print first 200 chars as preview
            text = event.get("full_text", "")
            print(f"Preview: {text[:200]}...")
        elif etype == "error":
            print(f"\nERROR: {event.get('message', '')}")

asyncio.run(main())
