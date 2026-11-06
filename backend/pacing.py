"""InsaneVoice — multi-speaker contextual pacing.

A conversation director for two or more cloned voices: silence length
between lines is chosen from the EMOTIONAL context of the previous line —
anger and excitement interrupt quickly, sadness and confusion let air in.
"""
from __future__ import annotations

import re

# tiny honest lexicon — no cloud, no model, just signal
URGENT = {"now", "go", "stop", "run", "fire", "quick", "hurry", "listen",
          "enough", "out", "damn", "move", "wait", "no", "yes", "never"}
SAD = {"sorry", "alone", "tired", "miss", "lost", "goodbye", "cry", "hurt",
       "gone", "empty", "remember", "why", "hopeless", "cold"}
HAPPY = {"great", "amazing", "love", "wow", "yes", "wonderful", "perfect",
         "awesome", "finally", "congrats", "happy", "brilliant"}


def sentiment(text: str) -> str:
    t = re.sub(r"\[[^\]]*\]", " ", text.lower())     # strip tags
    words = re.findall(r"[a-z']+", t)
    hits = sum(w in URGENT for w in words) + 2 * text.count("!")
    sad_hits = sum(w in SAD for w in words)
    happy_hits = sum(w in HAPPY for w in words) + text.count("😊") + text.count("!")
    if hits >= 2 or text.rstrip().endswith("!") and hits >= 1:
        return "urgent"
    if sad_hits >= 1 and sad_hits >= happy_hits:
        return "sad"
    if happy_hits >= 2:
        return "happy"
    if text.rstrip().endswith("?"):
        return "question"
    return "neutral"


GAPS = {
    "urgent": 0.12,     # interrupt fast
    "happy": 0.18,
    "neutral": 0.35,
    "question": 0.60,   # leave room for an answer
    "sad": 0.70,        # let the air sit
}


def gap_after(prev_line: str, explicit_pause: float | None = None) -> float:
    if explicit_pause is not None:
        return float(max(0.0, min(5.0, explicit_pause)))
    return GAPS[sentiment(prev_line)]


def plan_pauses(lines: list[dict]) -> list[dict]:
    """lines: [{text, pause?}] -> same list with computed gap_after values."""
    out = []
    nxt = 0.35
    for i, line in enumerate(lines):
        out.append({**line, "gap_before": round(nxt, 3)})
        nxt = gap_after(line["text"], line.get("pause"))
    return out
