"""End-to-end test: login, create story, stream via DeepSeek."""
import httpx, json, os, sys
from pathlib import Path

BASE = "http://127.0.0.1:8000"

# Login
resp = httpx.post(f"{BASE}/api/auth/login", json={"username": "alex", "password": "pass1234"})
token = resp.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Tier
tier = httpx.get(f"{BASE}/api/tiers/status", headers=headers).json()
print(f"Tier: {tier['tier']}")
print()

# Create story
resp = httpx.post(f"{BASE}/api/stories", headers=headers, json={
    "prompt": "A street musician in Prague discovers his violin can play notes that make people relive their happiest memory",
    "genre": "fantasy",
    "style": "descriptive",
    "max_words": 5000,
    "pov": "first_person",
})
story = resp.json()
story_id = story["id"]
print(f"Story ID: {story_id}")
print()

# Stream
print("=== Streaming (DeepSeek) ===\n")
with httpx.stream("GET", f"{BASE}/api/stories/{story_id}/stream", headers=headers, timeout=120) as r:
    for line in r.iter_lines():
        if not line.startswith("data:"):
            continue
        data = json.loads(line[5:].strip())
        etype = data.get("type", "?")

        if etype == "progress":
            print(f"  [{data.get('stage', '?')}] {data.get('message', '')}")
        elif etype == "chunk":
            print(data.get("text", ""), end="", flush=True)
        elif etype == "complete":
            print(f"\n\n=== Complete ===")
            print(f"  Title: {data.get('title', 'Untitled')}")
            print(f"  Words: {data.get('word_count', 0)}")
            print(f"  Sections: {data.get('section_count', '?')}")
        elif etype == "error":
            print(f"\n❌ ERROR: {data.get('message', '')}")
