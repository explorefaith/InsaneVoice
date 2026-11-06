"""InsaneVoice — Voice Design from a text description.

"young warm British female, a bit breathy, medium-slow"  ->  a designed voice.

How it works without any cloud model: the description is parsed into target
Voice DNA numbers, a base speaker reads a calibration sentence, and a small
DSP feedback loop (pitch shift + spectral tilt + tempo) pushes the sample
towards the targets, re-analysing after each pass (max 3). The shaped sample
becomes the voice: its speaker embedding is extracted like any other.
"""
from __future__ import annotations

import re

import dna
from emotions import apply_dsp

CALIBRATION = ("This is my designed voice. I can read your stories, your "
               "advertisements, and everything in between, in any language "
               "you write.")


def parse_description(desc: str) -> dict:
    d = (desc or "").lower()
    t = {"desc": desc}

    # pitch / gender-ish hints (Hz targets)
    female = any(w in d for w in ("female", "woman", "girl", "she ", "her "))
    male = any(w in d for w in ("male", "man", "guy", "boy", "he ", "his "))
    if re.search(r"\b(deep|bass|baritone|low)\b", d):
        t["f0"] = 95
    elif re.search(r"\b(soprano|very high|chirpy)\b", d):
        t["f0"] = 260
    elif female or re.search(r"\b(young)\b", d) and not male:
        t["f0"] = 205
    elif male:
        t["f0"] = 125
    else:
        t["f0"] = 165

    if re.search(r"\b(old|elderly|aged)\b", d):
        t["f0"] = int(t["f0"] * 0.93)
        t["rough"] = 55
    if re.search(r"\b(child|kid)\b", d):
        t["f0"] = 270

    t["warm"] = 70 if re.search(r"\b(warm|soft|gentle|cozy)\b", d) else 45
    if re.search(r"\b(bright|crisp|clear|energetic)\b", d):
        t["warm"] = min(t["warm"], 30)
    t["bright"] = 60 if re.search(r"\b(bright|crisp|clear)\b", d) else 35
    if re.search(r"\b(dark|deep|heavy)\b", d):
        t["bright"] = 15
    t["rough"] = t.get("rough", 55 if re.search(r"\b(rough|gritty|raspy|gravel)\b", d) else 25)
    t["breathy"] = 70 if re.search(r"\b(breathy|airy|whispery|soft)\b", d) else 35
    t["tempo"] = 0.92 if re.search(r"\b(slow|calm|gentle|measured)\b", d) else \
                 1.08 if re.search(r"\b(fast|quick|energetic|excited)\b", d) else 1.0

    if re.search(r"\b(british|uk|london)\b", d):
        t["accent"] = "en-br"
    elif re.search(r"\b(american|us|usa)\b", d):
        t["accent"] = "en-us"
    else:
        t["accent"] = None
    return t


def _dsp_from_delta(target: dict, actual: dict, pass_no: int) -> dict:
    p: dict = {}
    if target.get("f0") and actual.get("f0_median"):
        p["pitch"] = max(0.6, min(1.7, target["f0"] / max(actual["f0_median"], 1)))
        # soften per pass so the loop converges instead of oscillating
        p["pitch"] = 1 + (p["pitch"] - 1) * (1.0 if pass_no == 1 else 0.55)
    # spectral tilt: warm = down, bright = up (centroid mapping)
    t_cent = 900 + (target.get("bright", 35) / 100) * 2500
    a_cent = actual.get("spectral_centroid") or t_cent
    tilt_db = max(-6.0, min(6.0, 6.0 * (t_cent - a_cent) / max(t_cent, 1)))
    p["treble_db"] = round(tilt_db, 2)
    p["bass_db"] = round(-0.5 * tilt_db, 2) if target.get("warm", 45) > 55 else 0.0
    p["tempo"] = target.get("tempo", 1.0)
    if target.get("breathy", 0) > 55:
        p["lowpass"] = 5200
    return p


def design(speak_fn, workdir, targets: dict, max_passes: int = 3) -> dict:
    """speak_fn(text, out_wav) — usually locked to a base speaker."""
    import soundfile as sf

    workdir.mkdir(parents=True, exist_ok=True)
    current = workdir / "design_base.wav"
    speak_fn(CALIBRATION, current)
    report = {}
    for i in range(1, max_passes + 1):
        actual = dna.analyze(str(current))
        report = {"pass": i, "f0": actual["f0_median"],
                  "centroid": actual["spectral_centroid"],
                  "archetype": actual["archetype"]}
        p = _dsp_from_delta(targets, actual, i)
        shaped = workdir / f"design_pass{i}.wav"
        apply_dsp(current, shaped, p)
        current = shaped
        report["after"] = dna.analyze(str(current))["f0_median"]
        # stop when close
        if targets.get("f0") and abs(report["after"] - targets["f0"]) < max(12, targets["f0"] * 0.12):
            break
    dur = len(sf.read(str(current), dtype="float32")[0]) / 22050
    return {"file": current, "targets": targets, "report": report,
            "duration": round(dur, 2)}
