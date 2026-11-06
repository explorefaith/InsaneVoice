"""InsaneVoice — voice-ownership verification.

A candidate reads a random challenge aloud; we compare the VOICE METRICS of
that recording against the reference sample's Voice DNA. We check the voice
matches — not the words — using the same honest DSP as the analyser.
"""
from __future__ import annotations

import random

import dna

WORDS = [
    "harbor", "velvet", "signal", "meadow", "copper", "lantern", "whistle",
    "canyon", "spirit", "marble", "puzzle", "falcon", "orchid", "timber",
    "comet", "willow", "spiral", "ember", "cobalt", "meadow", "ripple",
    "stone", "gospel", "thunder", "orchard", "crystal", "harvest", "prairie",
]


def make_challenge(n: int = 5) -> list[str]:
    return random.sample(WORDS, n)


def check_challenge(ref_dna: dict, recording_path: str) -> dict:
    """Compare the recorded challenge against the reference DNA."""
    probe = dna.analyze(recording_path)

    def ratio(a, b):
        if not a or not b:
            return None
        return abs(a - b) / max(abs(b), 1e-9)

    checks = []
    f0_r = ratio(probe["f0_median"], ref_dna.get("f0_median"))
    checks.append({"metric": "pitch", "ratio": f0_r, "pass": f0_r is not None and f0_r <= 0.30})
    c_r = ratio(probe["spectral_centroid"], ref_dna.get("spectral_centroid"))
    checks.append({"metric": "brightness", "ratio": c_r, "pass": c_r is not None and c_r <= 0.45})
    f1_r = ratio(probe["formant_f1"], ref_dna.get("formant_f1"))
    checks.append({"metric": "formants", "ratio": f1_r, "pass": f1_r is not None and f1_r <= 0.50})

    hard = sum(1 for c in checks if c["pass"])
    passed = hard >= 2
    return {
        "passed": passed,
        "hard_passes": hard,
        "checks": checks,
        "probe": {k: probe[k] for k in
                  ("f0_median", "spectral_centroid", "formant_f1", "archetype")},
        "note": ("Voice metrics match the reference sample." if passed else
                 "Voice metrics do not match closely enough. Record in a similar "
                 "setting as your original sample."),
    }
