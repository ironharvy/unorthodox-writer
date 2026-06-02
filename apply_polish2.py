"""Second micro-polish: vary the near-verbatim 'I saw Umbra—ashen plain, violet sky,
line of cold' portal-glimpse so the recurring image evolves instead of repeating."""
from pathlib import Path

p = Path(__file__).resolve().parent / "novel.md"
text = p.read_text(encoding="utf-8")
EM = "—"

edits = [
    (
        f"The lens rotated. The beam swept its arc. At the apex, the shimmer opened, and I saw Umbra"
        f"{EM}the ashen plain, the violet sky, the line of cold creeping toward the city.",
        "The lens rotated. The beam swept its arc. At the apex, the shimmer opened, and there was "
        f"Umbra again{EM}the bruised dusk, the ash stretched flat to its too-near horizon, the pale "
        "cold gnawing closer to the city than it had been.",
    ),
    (
        f"and through the shimmer I saw Umbra waiting{EM}the ashen plain, the violet sky, the line of "
        f"cold creeping through the streets. For the first time in fourteen years,",
        "and Umbra was waiting on the other side, patient as it had always been—only the cold nearer "
        "the streets now than the night before. For the first time in fourteen years,",
    ),
]

for i, (old, new) in enumerate(edits, 1):
    if text.count(old) != 1:
        raise SystemExit(f"Edit {i}: expected 1 match, found {text.count(old)}")
    text = text.replace(old, new)

p.write_text(text, encoding="utf-8")
print("Applied", len(edits), "edits. Prose words:", end=" ")
import re
parts = re.split(r'\n##\s+Chapter \d+:[^\n]*\n', text)
print(sum(len(x.split()) for x in parts[1:]))
