"""InsaneVoice — emotional & non-verbal injection.

Script tags (case-insensitive):

    [pause 0.8]                 insert 0.8s of silence
    [sigh] [gasp] [breath]      synthesised non-verbal breath sounds
    [happy] ... [/happy]        style a span  (also: sad, angry, excited,
                                calm, serious, whisper)

Emotions are rendered with honest DSP on the synthesised segment — pitch,
tempo, spectral tilt, dynamics. Non-verbal exhales are synthesised from
filtered noise with shaped envelopes. [laughter] intentionally has no
synthetic equivalent: record a real chuckle and run it through the
Voice Changer — that is what it exists for.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 22050

EMOTIONS = {
    "happy":   {"pitch": 1.06, "tempo": 1.05, "treble_db": 2.0,  "bass_db": 0.0},
    "sad":     {"pitch": 0.92, "tempo": 0.88, "treble_db": -2.5, "bass_db": 0.5},
    "angry":   {"pitch": 1.03, "tempo": 1.08, "treble_db": 3.0,  "bass_db": 1.5},
    "excited": {"pitch": 1.10, "tempo": 1.12, "treble_db": 2.5,  "bass_db": 0.0},
    "calm":    {"pitch": 0.97, "tempo": 0.94, "treble_db": -1.0, "bass_db": 0.5},
    "serious": {"pitch": 0.96, "tempo": 0.96, "treble_db": -0.5, "bass_db": 1.0},
    "whisper": {"pitch": 0.98, "tempo": 0.92, "treble_db": -4.0, "bass_db": 0.0,
                "lowpass": 3600, "gain_db": 6.0, "noise": 0.018},
}

SPAN_TAGS = set(EMOTIONS)
INLINE_TAGS = {"pause", "sigh", "gasp", "breath"}
TAG_RE = re.compile(r"\[([a-zA-Z]+)(?:\s+([\d.]+))?\](?:([^[]*))(\[/\1\])?", re.I)


# ---------------- parsing ----------------

def parse_script(text: str) -> list[dict]:
    """-> [{kind: text|pause|sigh|gasp|breath, text, style: str|None}]"""
    segments: list[dict] = []
    stack: list[str] = []
    pos = 0
    for m in TAG_RE.finditer(text):
        before = text[pos:m.start()]
        if before.strip():
            segments.append({"kind": "text", "text": before.strip(),
                             "style": stack[-1] if stack else None})
        tag = m.group(1).lower()
        arg = m.group(2)
        inner = m.group(3) or ""
        closing = bool(m.group(4))
        if tag in SPAN_TAGS:
            if closing and stack and stack[-1] == tag:
                stack.pop()
            elif not closing:
                stack.append(tag)
            if inner.strip():
                segments.append({"kind": "text", "text": inner.strip(),
                                 "style": stack[-1] if stack else None})
        elif tag == "pause":
            dur = max(0.05, min(5.0, float(arg) if arg else 0.5))
            segments.append({"kind": "pause", "dur": dur, "style": None})
        elif tag in ("sigh", "gasp", "breath"):
            segments.append({"kind": tag, "style": None})
        # unknown tags are ignored silently
        pos = m.end()
    tail = text[pos:]
    if tail.strip():
        segments.append({"kind": "text", "text": tail.strip(),
                         "style": stack[-1] if stack else None})
    return segments


def has_tags(text: str) -> bool:
    return bool(TAG_RE.search(text or ""))


# ---------------- non-verbal synthesis ----------------

def _write(path: Path, x: np.ndarray) -> None:
    peak = np.max(np.abs(x)) or 1.0
    sf.write(str(path), (x / peak * 0.85).astype(np.float32), SR)


def synth_nonverbal(kind: str, out_path: Path) -> Path:
    rng = np.random.default_rng(42)
    if kind == "pause":
        _write(out_path, np.zeros(int(0.4 * SR), dtype=np.float32))
    elif kind == "sigh":
        dur = 1.25
        t = np.linspace(0, dur, int(dur * SR), endpoint=False)
        noise = rng.standard_normal(len(t)).astype(np.float32)
        # exhalation: lowpass sweeping down + envelope swell→decay
        cut = np.linspace(2400, 380, len(t))
        alpha = np.exp(-2 * np.pi * cut / SR).astype(np.float32)
        y = np.zeros_like(t)
        acc = 0.0
        for i in range(len(t)):
            acc = (1 - alpha[i]) * noise[i] + alpha[i] * acc
            y[i] = acc
        env = np.minimum(t / 0.18, 1.0) * np.exp(-2.6 * np.maximum(t - 0.25, 0) / dur)
        _write(out_path, (y * env * 1.6).astype(np.float32))
    elif kind == "gasp":
        dur = 0.38
        t = np.linspace(0, dur, int(dur * SR), endpoint=False)
        noise = rng.standard_normal(len(t)).astype(np.float32)
        # bandpass-ish: difference of two one-pole lows
        a1 = np.exp(-2 * np.pi * 2800 / SR)
        a2 = np.exp(-2 * np.pi * 700 / SR)
        y = np.zeros_like(t); lo1 = 0.0; lo2 = 0.0
        for i in range(len(t)):
            lo1 = (1 - a1) * noise[i] + a1 * lo1
            lo2 = (1 - a2) * noise[i] + a2 * lo2
            y[i] = lo1 - lo2
        env = np.exp(-9 * t) * (1 - np.exp(-160 * t))
        _write(out_path, (y * env * 2.2).astype(np.float32))
    elif kind == "breath":
        dur = 0.65
        t = np.linspace(0, dur, int(dur * SR), endpoint=False)
        noise = rng.standard_normal(len(t)).astype(np.float32)
        a = np.exp(-2 * np.pi * 1500 / SR)
        y = np.zeros_like(t); acc = 0.0
        for i in range(len(t)):
            acc = (1 - a) * noise[i] + a * acc
            y[i] = acc
        env = np.sin(np.pi * t / dur) ** 1.5
        _write(out_path, (y * env * 0.9).astype(np.float32))
    else:
        raise ValueError(f"unknown non-verbal {kind}")
    return out_path


# ---------------- emotion DSP (ffmpeg) ----------------

def _atempo_chain(t: float) -> str:
    parts = []
    v = t
    while v > 2.0:
        parts.append("atempo=2.0"); v /= 2.0
    while v < 0.5:
        parts.append("atempo=0.5"); v /= 0.5
    parts.append(f"atempo={v:.4f}")
    return ",".join(parts)


def apply_dsp(in_wav: Path, out_wav: Path, p: dict) -> None:
    filters = []
    if abs(p.get("pitch", 1.0) - 1.0) > 1e-3:
        filters.append(f"asetrate={SR * p['pitch']:.0f},aresample={SR}")
        filters.append(_atempo_chain(1.0 / p["pitch"]))          # keep duration
    if abs(p.get("tempo", 1.0) - 1.0) > 1e-3:
        filters.append(_atempo_chain(p["tempo"]))
    if p.get("bass_db"):
        filters.append(f"bass=g={p['bass_db']}:f=220")
    if p.get("treble_db"):
        filters.append(f"treble=g={p['treble_db']}:f=3200")
    if p.get("lowpass"):
        filters.append(f"lowpass=f={p['lowpass']}")
    if p.get("gain_db"):
        filters.append(f"volume={p['gain_db']}dB")
    base = ",".join(filters) or "anull"

    if p.get("noise"):
        # whisper breath bed: mix in quiet filtered noise
        bed = out_path.with_name(out_path.stem + "_bed.wav")
        n = len(sf.read(str(in_wav), dtype="float32")[0])
        rng = np.random.default_rng(7)
        t = np.arange(n) / SR
        air = rng.standard_normal(n).astype(np.float32) * 0.5
        sf.write(str(bed), air, SR)
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
               "-i", str(in_wav), "-i", str(bed),
               "-filter_complex",
               f"[1:a]lowpass=f=3400,highpass=f=800,volume={p['noise']}[b];"
               f"[0:a]{base}[s];[s][b]amix=inputs=2:duration=first:normalize=0",
               str(out_wav)]
        bed.unlink(missing_ok=True)
    else:
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
               "-i", str(in_wav), "-af", base, str(out_wav)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=180)


# ---------------- segment concat ----------------

def concat_wavs(parts: list[Path], out: Path, gap: float = 0.09) -> Path:
    """numpy-level concat with small gaps (all are SR mono float32)."""
    g = np.zeros(int(gap * SR), dtype=np.float32)
    pieces = []
    for i, p in enumerate(parts):
        x, sr = sf.read(str(p), dtype="float32", always_2d=True)
        if sr != SR:
            import subprocess as sp
            tmp = p.with_suffix(".r.wav")
            sp.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(p),
                    "-ar", str(SR), "-ac", "1", str(tmp)], check=True)
            x, _ = sf.read(str(tmp), dtype="float32", always_2d=True)
            tmp.unlink(missing_ok=True)
        pieces.append(x.mean(axis=1))
        if i < len(parts) - 1:
            pieces.append(g)
    sf.write(str(out), np.concatenate(pieces).astype(np.float32), SR)
    return out


# ---------------- the full emotional render ----------------

def render_emotional(text: str, workdir: Path, speak_fn, gap: float = 0.09) -> dict:
    """speak_fn(text, out_wav) renders one plain-text segment; we handle the rest.

    Returns {file, timeline:[{kind,text?,style?,dur}], warnings}
    """
    workdir.mkdir(parents=True, exist_ok=True)
    segments = parse_script(text)
    parts: list[Path] = []
    timeline: list[dict] = []
    warnings: list[str] = []
    idx = 0

    for seg in segments:
        out = workdir / f"seg_{idx:03d}.wav"
        if seg["kind"] == "text":
            raw = workdir / f"raw_{idx:03d}.wav"
            speak_fn(seg["text"], raw)
            style = seg.get("style")
            if style and style in EMOTIONS:
                try:
                    apply_dsp(raw, out, EMOTIONS[style])
                    raw.unlink(missing_ok=True)
                except Exception:
                    warnings.append(f"DSP failed for a '{style}' segment; used plain audio.")
                    raw.replace(out)
            else:
                raw.replace(out)
            dur = len(sf.read(str(out), dtype="float32")[0]) / SR
            timeline.append({"kind": "text", "text": seg["text"], "style": style, "dur": round(dur, 2)})
        else:
            synth_nonverbal(seg["kind"], out)
            dur = seg.get("dur") if seg["kind"] == "pause" else None
            if seg["kind"] == "pause":
                sf.write(str(out), np.zeros(int(dur * SR), dtype=np.float32), SR)
            dur = len(sf.read(str(out), dtype="float32")[0]) / SR
            timeline.append({"kind": seg["kind"], "dur": round(dur, 2)})
        parts.append(out)
        idx += 1

    final = workdir / "emotional_full.wav"
    concat_wavs(parts, final, gap=gap)
    total = len(sf.read(str(final), dtype="float32")[0]) / SR
    return {"file": final, "timeline": timeline, "total": round(total, 2),
            "warnings": warnings}
