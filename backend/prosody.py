"""InsaneVoice — prosody humanizer.

MeloTTS speaks in a perfectly even, monotone rhythm, and OpenVoice transfers
only the tone colour — so that robotic rhythm survives the clone. This module
makes the speech behave like a recording instead of a synthesiser:

    pre-conversion  (engine.generate)
      - sentence segmentation on silence
      - phrase-final intonation (declarative fall / question rise) applied as
        a smooth pitch envelope per sentence
      - per-sentence micro speed + gain jitter
      - human gap-length variance between sentences

    post-conversion
      - soft breaths at sentence boundaries
      - room-tone floor (removes the "digital silence" tell)
      - gentle high-pass + peak normalise
"""
from __future__ import annotations

import numpy as np
import soundfile as sf

FRAME_MS = 25
HOP_MS = 10
MIN_SEG_S = 0.35          # ignore shorter "sentences"
MIN_GAP_S = 0.10          # human pauses never shorter
MAX_GAP_S = 0.34          # ... or this long
CROSSFADE_S = 0.045       # crossfade between pitch-shift zones
BREATH_DB = -29.0         # peak level of inserted breaths


# ---------- helpers ----------

def _frames(x: np.ndarray, sr: int):
    fl = int(sr * FRAME_MS / 1000)
    hp = int(sr * HOP_MS / 1000)
    n = max(1, (len(x) - fl) // hp + 1)
    idx = np.arange(fl)[None, :] + hp * np.arange(n)[:, None]
    return x[idx], hp


def _rms_frames(x: np.ndarray, sr: int) -> np.ndarray:
    fr, _ = _frames(x, sr)
    return np.sqrt(np.mean(fr ** 2, axis=1))


def _split_sentences(x: np.ndarray, sr: int) -> list[tuple[int, int]]:
    """Speech runs separated by >= 0.18s of silence."""
    rms = _rms_frames(x, sr)
    thr = max(0.012, 0.06 * float(np.percentile(rms, 95)))
    voiced = rms >= thr
    hp = int(sr * HOP_MS / 1000)
    segs, start, gap = [], None, 0
    min_gap_fr = int(0.18 / (HOP_MS / 1000))
    for i, v in enumerate(voiced):
        if v:
            if start is None:
                start = i
            gap = 0
        elif start is not None:
            gap += 1
            if gap >= min_gap_fr:
                segs.append((start, i - gap + 1))
                start, gap = None, 0
    if start is not None:
        segs.append((start, len(voiced)))
    out = []
    for a, b in segs:
        s, e = a * hp, min(len(x), (b * hp) + int(sr * FRAME_MS / 1000))
        if (e - s) / sr >= MIN_SEG_S:
            out.append((s, e))
    return out


def _shift_zone(y: np.ndarray, sr: int, steps: float) -> np.ndarray:
    import librosa
    return librosa.effects.pitch_shift(y, sr=sr, n_steps=float(steps))


def _apply_envelope(seg: np.ndarray, sr: int, s_start: float, s_mid: float,
                    s_end: float) -> np.ndarray:
    """Three pitch zones (start/mid/end) joined with equal-power crossfades."""
    n = len(seg)
    if n < int(sr * 0.6) or n < 2048:
        # too short to contour meaningfully
        return seg if abs(s_mid) < 1e-3 else _shift_zone(seg, sr, s_mid)
    b1, b2 = int(n * 0.42), int(n * 0.76)
    w = min(int(CROSSFADE_S * sr), n // 5)
    a = _shift_zone(seg, sr, s_start)
    b = _shift_zone(seg, sr, s_mid)
    c = _shift_zone(seg, sr, s_end)
    out = a.copy()
    # zone b fades in over [b1, b1+w) and zone c over [b2, b2+w)
    e1 = min(n, b1 + w)
    fade = np.linspace(0, np.pi / 2, max(2, e1 - b1))
    out[b1:e1] = a[b1:e1] * np.cos(fade) + b[b1:e1] * np.sin(fade)
    out[e1:b2] = b[e1:b2]
    e2 = min(n, b2 + w)
    fade2 = np.linspace(0, np.pi / 2, max(2, e2 - b2))
    out[b2:e2] = b[b2:e2] * np.cos(fade2) + c[b2:e2] * np.sin(fade2)
    out[e2:] = c[e2:]
    return out


def _time_stretch(y: np.ndarray, sr: int, rate: float) -> np.ndarray:
    """WSOLA via ffmpeg atempo — far cleaner than a phase vocoder, and it
    keeps the speaker embedding intact (phase-vocoder smearing does not)."""
    if abs(rate - 1.0) < 1e-3 or len(y) < 2048:
        return y
    import subprocess, tempfile, os
    rate = float(np.clip(rate, 0.5, 2.0))
    # chain atempo for rates outside [0.5, 2] (not needed with our jitter)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fin, \
         tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fout:
        fin_name, fout_name = fin.name, fout.name
    try:
        sf.write(fin_name, y, sr)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", fin_name,
                        "-af", f"atempo={rate:.5f}", "-ar", str(sr),
                        "-ac", "1", fout_name],
                       check=True, capture_output=True, timeout=60)
        out, _ = sf.read(fout_name, dtype="float32", always_2d=True)
        return out.mean(axis=1)
    except Exception:
        return y
    finally:
        for p in (fin_name, fout_name):
            os.unlink(p)


def _sentence_is_question(text: str | None) -> bool:
    return bool(text) and text.strip().endswith("?")


def split_sentences(text: str) -> list[str]:
    """Split a script into sentences so audio segments can be aligned."""
    import re
    return [p.strip() for p in re.split(r"(?<=[.!?…])\s+", (text or "").strip())
            if p.strip()]


def split_clauses(sentence: str) -> list[str]:
    """Split a sentence at commas/semicolons/dashes into spoken phrases."""
    import re
    parts = re.split(r"(?<=[,;—–:])\s+", sentence.strip())
    return [p for p in parts if p.strip()] or [sentence.strip()]


def contour_clause(seg: np.ndarray, sr: int, kind: str,
                   rng: np.random.Generator, intensity: float = 1.0) -> np.ndarray:
    """Phrase-level intonation.

    kind: "final_fall"  — sentence end, declarative: clear terminal fall
          "final_rise" — sentence end, question: rise
          "continuation" — clause followed by more speech: level/slight fall
    """
    if kind == "final_rise":
        s0, s1, s2 = rng.uniform(0.25, 0.55), rng.uniform(0.0, 0.3), rng.uniform(0.9, 1.5)
    elif kind == "continuation":
        s0, s1, s2 = rng.uniform(0.05, 0.3), rng.uniform(-0.1, 0.15), rng.uniform(-0.4, 0.05)
    else:
        s0, s1, s2 = rng.uniform(0.15, 0.5), rng.uniform(-0.1, 0.2), rng.uniform(-1.35, -0.65)
    return _apply_envelope(seg, sr, s0 * intensity, s1 * intensity,
                           s2 * intensity)


def final_lengthen(seg: np.ndarray, sr: int, frac: float = 0.14,
                   rate: float = 0.92) -> np.ndarray:
    """Phrase-final lengthening: the last syllables slow down, like real speech."""
    n = len(seg)
    k = int(n * frac)
    if k < 2048 or n < 4000:
        return seg
    head, tail = seg[:n - k], seg[n - k:]
    return np.concatenate([head, _time_stretch(tail, sr, rate)])


def assemble(clause_groups: list[list[np.ndarray]], sr: int,
             rng: np.random.Generator) -> tuple[np.ndarray, list[float]]:
    """Join rendered clauses with micro-gaps (clauses) and human gaps
    (sentences). Returns the assembled audio and the sentence-join times
    (for breath placement in finish())."""
    pieces: list[np.ndarray] = []
    joins: list[float] = []
    t = 0.0
    n_g = len(clause_groups)
    for gi, group in enumerate(clause_groups):
        n_c = len(group)
        for ci, x in enumerate(group):
            pieces.append(x)
            t += len(x) / sr
            if ci < n_c - 1:
                gap = rng.uniform(0.05, 0.11)      # clause micro-pause
            elif gi < n_g - 1:
                gap = rng.uniform(0.14, 0.30)      # sentence pause
                joins.append(t + gap * 0.55)
            else:
                continue
            pieces.append(np.zeros(int(gap * sr), dtype=np.float32))
            t += gap
    y = np.concatenate(pieces) if len(pieces) > 1 else pieces[0]
    peak = float(np.max(np.abs(y))) or 1.0
    if peak > 0.99:
        y *= 0.99 / peak
    return y, joins


# ---------- pre-conversion pass ----------

def humanize(in_wav, out_wav, sentences: list[str] | None = None,
             intensity: float = 1.0, rng: np.random.Generator | None = None):
    """Re-render the base speech with human-like rhythm and intonation.

    Returns the list of boundary (seconds) where sentences join — used later
    by finish() to place breaths (tone conversion preserves duration).
    """
    rng = rng or np.random.default_rng()
    x, sr = sf.read(str(in_wav), dtype="float32", always_2d=True)
    x = x.mean(axis=1)
    segs = _split_sentences(x, sr)
    if not segs or len(segs) == 0:
        sf.write(str(out_wav), x, sr)
        return []

    aligned = sentences if sentences and len(sentences) == len(segs) else None
    lead_n = min(segs[0][0], int(0.15 * sr))
    parts, gaps = [x[:lead_n]], []

    for i, (s, e) in enumerate(segs):
        seg = x[s:e].copy()
        rate = 1.0 + rng.uniform(-0.045, 0.055) * intensity
        gain = 10 ** (rng.uniform(-1.0, 1.0) * intensity / 20)
        seg = _time_stretch(seg, sr, rate)
        if _sentence_is_question(aligned[i] if aligned else None):
            s0, s1, s2 = (rng.uniform(0.2, 0.5), rng.uniform(0.0, 0.25),
                          rng.uniform(0.7, 1.3))
        else:
            s0, s1, s2 = (rng.uniform(0.1, 0.45), rng.uniform(-0.15, 0.15),
                          rng.uniform(-1.2, -0.5))
        seg = _apply_envelope(seg, sr, s0 * intensity, s1 * intensity,
                              s2 * intensity)
        seg *= gain
        parts.append(seg)
        if i < len(segs) - 1:
            src_gap = segs[i + 1][0] - e
            target = np.clip(src_gap / sr, MIN_GAP_S, MAX_GAP_S)
            target += rng.uniform(-0.02, 0.06) * intensity
            target = float(np.clip(target, MIN_GAP_S, MAX_GAP_S + 0.05))
            gaps.append(target)

    # rebuild: seg / gap / seg ... recording each join time for finish()
    out = [parts[0]]
    placed = [float(len(parts[0]) / sr)]      # running timeline (seconds)
    bounds = []
    for i, seg in enumerate(parts[1:]):
        out.append(seg)
        if i < len(gaps):
            g = np.zeros(int(gaps[i] * sr), dtype=np.float32)
            out.append(g)
            placed.append(placed[-1] + len(seg) / sr)
            bounds.append(placed[-1])
            placed.append(placed[-1] + gaps[i])
    y = np.concatenate(out) if len(out) > 1 else out[0]
    # trailing: keep a short natural tail
    tail = x[segs[-1][1]:]
    if len(tail) > int(0.4 * sr):
        tail = tail[:int(0.4 * sr)]
    y = np.concatenate([y, tail]) if len(tail) else y

    peak = float(np.max(np.abs(y))) or 1.0
    if peak > 0.99:
        y *= 0.99 / peak
    sf.write(str(out_wav), y, sr)
    return bounds


# ---------- post-conversion pass ----------

def _breath(sr: int, dur: float, rng) -> np.ndarray:
    """Soft inhale: band-passed noise with a fast-attack, slow-decay envelope."""
    from scipy.signal import butter, sosfilt
    n = int(dur * sr)
    noise = rng.standard_normal(n).astype(np.float32)
    sos = butter(2, [280, 2200], btype="bandpass", fs=sr, output="sos")
    y = sosfilt(sos, noise).astype(np.float32)
    at = max(2, int(0.03 * sr))
    env = np.exp(-np.linspace(0.0, 4.5, n)).astype(np.float32)
    env[:at] *= np.linspace(0, 1, at)
    y *= env
    y /= (np.max(np.abs(y)) or 1.0)
    return y * (10 ** (BREATH_DB / 20)) * rng.uniform(0.75, 1.15)


def finish(in_wav, out_wav, bounds: list[float], breath_ratio: float = 0.55,
           rng: np.random.Generator | None = None) -> None:
    """Add breaths at sentence joins, clean up DC/rumble.

    NOTE: no room-tone/noise floor here on purpose — OpenVoice's speaker
    encoder is hypersensitive to broadband noise spread over the file (even
    at -55 dB it measurably wrecked clone similarity), and the converter's
    vocoder already leaves a natural-sounding noise floor.
    """
    rng = rng or np.random.default_rng()
    x, sr = sf.read(str(in_wav), dtype="float32", always_2d=True)
    mono = x.mean(axis=1)
    for b in bounds:
        if b <= 0 or b * sr >= len(mono) - sr * 0.2:
            continue
        if rng.random() > breath_ratio:
            continue
        dur = rng.uniform(0.11, 0.18)
        br = _breath(sr, dur, rng)
        i0 = int(b * sr) - len(br) // 3          # start just inside the gap
        i1 = min(len(mono), i0 + len(br))
        if i0 < 0:
            continue
        mono[i0:i1] += br[:i1 - i0]
    from scipy.signal import butter, sosfilt
    sos = butter(2, 65, btype="highpass", fs=sr, output="sos")
    mono = sosfilt(sos, mono).astype(np.float32)
    peak = float(np.max(np.abs(mono))) or 1.0
    if peak > 0.95:
        mono *= 0.95 / peak
    sf.write(str(out_wav), mono, sr)
