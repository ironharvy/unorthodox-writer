"""Quick DeepSeek test: generate a story through the Unorthodox Writer engine."""
import asyncio, os, sys
from pathlib import Path

# Load DeepSeek key from Hermes env
env_path = Path.home() / ".hermes" / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if line.startswith("DEEPSEEK_API_KEY="):
            os.environ["DEEPSEEK_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")
        if line.startswith("DEEPSEEK_BASE_URL="):
            os.environ["DEEPSEEK_BASE_URL"] = line.split("=", 1)[1].strip().strip('"').strip("'")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine.pipeline import StoryPipeline

async def main():
    pipeline = StoryPipeline(
        tier="paid",
        cloud_provider="deepseek",
        cloud_model="deepseek-chat",
        cloud_max_tokens=2048,
    )
    
    prompt = "A lighthouse keeper discovers the light is actually a portal to another world"
    
    print("🔥 Generating story with DeepSeek...\n")
    async for event in pipeline.generate(
        prompt=prompt,
        genre="fantasy",
        style="descriptive",
        max_words=300,
        pov="first_person",
    ):
        etype = event.get("type", "?")
        if etype == "progress":
            print(f"  [{event.get('stage', '?')}] {event.get('message', '')}")
        elif etype == "chunk":
            print(event.get("text", ""), end="", flush=True)
        elif etype == "complete":
            print(f"\n\n✅ Story complete! {event.get('word_count', 0)} words")
            print(f"   Title: {event.get('title', 'Untitled')}")
        elif etype == "error":
            print(f"\n❌ Error: {event.get('message', '')}")

asyncio.run(main())
