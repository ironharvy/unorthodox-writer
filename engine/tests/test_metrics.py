"""
Unit tests for engine/metrics.py — all deterministic, no network.
"""

from engine.metrics import StoryMetrics, format_report


CLEAN_PROSE = (
    "The harbor went quiet at dusk. Gulls settled on the pilings. "
    "Mara counted the boats as they came in, one by one, and named each "
    "for its captain. \"You're late,\" she told the last of them, though no "
    "one answered. The water held the last of the light and let it go. "
    "She walked home along the seawall, slow, listening to the tide work "
    "the stones. Tomorrow the nets would need mending. Tonight she only "
    "wanted the cold air and the sound of the sea breathing."
)

ARTIFACT_PROSE = (
    "However, the tapestry of fate was a testament to the human spirit. "
    "Moreover, she would delve into the complexities. Furthermore, it was "
    "a stark reminder. Indeed, the palpable tension sent shivers down her "
    "spine. In conclusion, she couldn't help but navigate the complexities "
    "of the intricate, ever-present, woven tapestry of destiny."
)


def test_compute_returns_expected_keys():
    m = StoryMetrics().compute(CLEAN_PROSE)
    for key in ("ai_artifact_score", "readability", "sentence_variety",
                "dialogue_ratio", "pacing_balance", "repetition_score",
                "subscores", "overall", "word_count"):
        assert key in m


def test_scores_in_range():
    m = StoryMetrics().compute(CLEAN_PROSE)
    assert 0 <= m["ai_artifact_score"] <= 10
    assert 0 <= m["repetition_score"] <= 10
    assert 0 <= m["overall"] <= 10


def test_artifact_detection_distinguishes():
    clean = StoryMetrics().compute(CLEAN_PROSE)["ai_artifact_score"]
    dirty = StoryMetrics().compute(ARTIFACT_PROSE)["ai_artifact_score"]
    assert dirty > clean
    assert dirty >= 3.0, f"riddled prose should score high, got {dirty}"


def test_repetition_detection():
    sm = StoryMetrics()
    phrase = "the air tasted of copper and cold stone and rot. "
    repeated = phrase * 6 + "She walked on through the empty hall to the door."
    score = sm.compute(repeated)["repetition_score"]
    assert score > 0
    repeats = sm.repeated_phrases(repeated, min_count=3)
    assert any("copper and cold stone" in p for p, _ in repeats)


def test_no_repetition_on_clean_text():
    assert StoryMetrics().compute(CLEAN_PROSE)["repetition_score"] == 0.0


def test_dialogue_ratio():
    sm = StoryMetrics()
    no_dialogue = "The room was empty and the light was gray and nothing moved at all."
    heavy = '"Hello there," she said. "How are you today, my old friend?" he asked.'
    assert sm.compute(no_dialogue)["dialogue_ratio"] == 0.0
    assert sm.compute(heavy)["dialogue_ratio"] > 0.3


def test_pacing_with_explicit_counts():
    sm = StoryMetrics()
    even = sm.compute("x", chapter_word_counts=[500, 510, 495, 505])["pacing_balance"]
    uneven = sm.compute("x", chapter_word_counts=[100, 900, 200, 1500])["pacing_balance"]
    assert even < uneven
    assert even < 0.3


def test_pacing_detects_chapter_headers():
    text = (
        "# Title\n\n## Chapter 1: A\n\n" + " ".join(["w"] * 100) +
        "\n\n## Chapter 2: B\n\n" + " ".join(["w"] * 100) +
        "\n\n## Chapter 3: C\n\n" + " ".join(["w"] * 100)
    )
    cv = StoryMetrics().compute(text)["pacing_balance"]
    assert cv is not None
    assert cv < 0.05  # near-identical chapter lengths


def test_sentence_variety_zero_for_uniform():
    uniform = "The cat sat down. The dog ran fast. The bird flew high. The fish swam deep."
    std = StoryMetrics().compute(uniform)["sentence_variety"]
    assert std < 2.0


def test_clean_prose_beats_artifact_prose_overall():
    clean = StoryMetrics().compute(CLEAN_PROSE)["overall"]
    dirty = StoryMetrics().compute(ARTIFACT_PROSE)["overall"]
    assert clean > dirty


def test_format_report_runs():
    m = StoryMetrics().compute(CLEAN_PROSE)
    report = format_report(CLEAN_PROSE, m, label="test")
    assert "OVERALL" in report
    assert "AI artifact" in report
