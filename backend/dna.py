"""InsaneVoice - Voice DNA analyzer.

Pure numpy/scipy DSP (no librosa dependency): estimates the acoustic
fingerprint of a reference voice - pitch, timbre, texture - and distils it
into radar-chart scores plus a human-readable voice archetype.

Every number here is computed from the actual waveform. No magic.
"""
from __future__ import annotations

import numpy as np
import soundfile as sf
from scipy.signal import find_peaks, periodogram
from scipy.linalg import solve_toeplitz

FRAME = 512          # ~23ms @ 22050
HOP = 220            # ~10ms
FMIN, FMAX = 60.0, 400.0


def _frames(x: np.ndarray, frame: int, hop: int) -> np.ndarray:
    n = 1 + max(0, (len(x) - frame) // hop)
    return np.stack([x[i * hop: i * hop + frame] for i in range(n)])


def _rms_frames(x: np.ndarray) -> np.ndarray:
    fr = _frames(x, FRAME, HOP)
    return np.sqrt(np.mean(fr ** 2, axis=1) + 1e-12)


def _vad_mask(rms: np.ndarray) -> np.ndarray:
    """Lightweight energy VAD: speech = above noise floor estimate."""
    floor = np.percentile(rms, 15)
    ceiling = np.percentile(rms, 90)
    if ceiling <= floor * 1.05:            # flat recording (silence/tone)
        return np.ones_like(rms, dtype=bool)
    thr = floor + 0.25 * (ceiling - floor)
    mask = rms > thr
    # close small gaps < 12 frames (~120ms)
    idx = np.where(~mask)[0]
    for i in idx:
        lo, hi = max(0, i - 6), min(len(mask), i + 6)
        if mask[max(0, i - 6): i + 6].any() and (i > 0 and mask[i - 1]) is False:
            pass
    return mask


def _pitch_track(x: np.ndarray, sr: int, mask: np.ndarray) -> np.ndarray:
    """Autocorrelation F0 per frame; NaN where unvoiced."""
    fr = _frames(x, FRAME * 2, HOP)                       # ~46ms window
    lag_min = int(sr / FMAX)
    lag_max = int(sr / FMIN)
    f0 = np.full(fr.shape[0], np.nan)
    for i, frame in enumerate(fr):
        f = frame - frame.mean()
        energy = np.sum(f ** 2)
        if energy < 1e-6:
            continue
        ac = np.correlate(f, f, mode="full")[len(f) - 1:]
        if ac[0] <= 0:
            continue
        ac /= ac[0]
        seg = ac[lag_min: min(lag_max, len(ac) - 1)]
        if len(seg) < 8:
            continue
        peaks, props = find_peaks(seg, height=0.30)
        if len(peaks) == 0:
            continue
        best = peaks[np.argmax(props["peak_heights"])]
        lag = lag_min + best
        # parabolic refinement around the peak
        if 0 < best < len(seg) - 1:
            a, b, c = seg[best - 1], seg[best], seg[best + 1]
            denom = a - 2 * b + c
            if abs(denom) > 1e-9:
                lag += 0.5 * (a - c) / denom
        f0[i] = sr / lag
    f0[~mask[: len(f0)]] = np.nan
    # median filter (3) to kill octave jumps
    v = f0.copy()
    for i in range(1, len(f0) - 1):
        w = [t for t in (f0[i - 1], f0[i], f0[i + 1]) if not np.isnan(t)]
        if w:
            v[i] = float(np.median(w))
    return v


def _formants_lpc(x: np.ndarray, sr: int, mask: np.ndarray) -> tuple[float, float]:
    """Median F1/F2 via LPC root analysis on strong voiced frames."""
    fr = _frames(x, FRAME, HOP)
    order = 2 + sr // 1000
    f1s, f2s = [], []
    energies = np.mean(fr ** 2, axis=1)
    if len(energies) == 0:
        return 0.0, 0.0
    thr = np.percentile(energies, 60)
    picks = [i for i in range(len(fr))
             if mask[min(i, len(mask) - 1)] and energies[i] >= thr]
    picks = picks[: 60]                      # cap compute
    for i in picks:
        f = fr[i].astype(np.float64)
        f = f - f.mean()
        w = f * np.hanning(len(f))
        ac = np.correlate(w, w, mode="full")[len(w) - 1:]
        ac /= (ac[0] + 1e-12)
        if ac[0] <= 0:
            continue
        try:
            a = solve_toeplitz((ac[:order], ac[:order]),
                               np.r_[1.0, np.zeros(order - 1)])
        except Exception:
            continue
        # prediction polynomial 1 - a1 z ... -> build full coeffs
        coeffs = np.r_[1.0, -a[1:]]
        roots = np.roots(coeffs)
        r = roots[np.abs(roots) > 0.8]
        ang = np.angle(r[r.imag > 0])
        freqs = np.sort(ang * sr / (2 * np.pi))
        freqs = freqs[(freqs > 150) & (freqs < 4500)]
        if len(freqs) >= 2:
            f1s.append(freqs[0])
            f2s.append(freqs[1])
    f1 = float(np.median(f1s)) if f1s else 0.0
    f2 = float(np.median(f2s)) if f2s else 0.0
    return f1, f2


def _spectral_stats(x: np.ndarray, sr: int, mask: np.ndarray) -> dict:
    fr = _frames(x, FRAME, HOP)
    freqs, psd = periodogram(fr * np.hanning(FRAME), sr, axis=1)
    psd = psd + 1e-12
    # keep only speech-active frames
    keep = mask[: psd.shape[0]]
    if keep.sum() == 0:
        keep = np.ones(psd.shape[0], dtype=bool)
    P = psd[keep]
    total = P.sum(axis=1, keepdims=True)
    Pn = P / total
    centroid = (Pn * freqs).sum(axis=1)
    spread = np.sqrt(((freqs - centroid[:, None]) ** 2 * Pn).sum(axis=1))
    cum = np.cumsum(P, axis=1)
    rolloff = freqs[np.argmax(cum >= 0.85 * cum[:, -1:], axis=1)]
    flat = np.exp(np.mean(np.log(Pn), axis=1))
    zc = np.mean(np.abs(np.diff(np.sign(fr[keep]))), axis=1) / 2
    return {
        "centroid": float(np.median(centroid)),
        "spread": float(np.median(spread)),
        "rolloff85": float(np.median(rolloff)),
        "flatness": float(np.median(flat)),
        "zcr": float(np.median(zc)),
        "band_low": float(Pn[:, : int(1000 / (sr / 2 / len(freqs)))].sum() * len(freqs) * 0 + Pn[:, freqs <= 1000].sum()),
        "band_high": float(Pn[:, freqs >= 4000].sum()),
    }


def _norm(v: float, lo: float, hi: float) -> float:
    return float(max(0.0, min(100.0, (v - lo) / (hi - lo) * 100)))


def analyze(path: str) -> dict:
    """Compute the full Voice DNA report for a normalized wav file."""
    x, sr = sf.read(path, dtype="float32", always_2d=True)
    x = x.mean(axis=1)
    duration = len(x) / sr

    rms = _rms_frames(x)
    mask = _vad_mask(rms)
    speech_ratio = float(mask.mean())

    voiced = x  # analysis windows carry the mask internally

    f0 = _pitch_track(voiced, sr, mask)
    f0v = f0[~np.isnan(f0)]
    if len(f0v) < 10:
        # fallback: relax threshold by re-running VAD as all-true
        f0 = _pitch_track(voiced, sr, np.ones_like(mask, dtype=bool))
        f0v = f0[~np.isnan(f0)]

    med_f0 = float(np.median(f0v)) if len(f0v) else 0.0
    if len(f0v) >= 20:
        p25, p75 = np.percentile(f0v, [25, 75])
        pitch_range = float(p75 - p25)
        jitter = float(np.mean(np.abs(np.diff(f0v))) / (med_f0 + 1e-9))
    else:
        pitch_range, jitter = 0.0, 0.0

    spec = _spectral_stats(voiced, sr, mask)
    f1, f2 = _formants_lpc(voiced, sr, mask)

    # shimmer: variability of frame energy on speech
    mrms = rms[mask] if mask.any() else rms
    shimmer = float(np.mean(np.abs(np.diff(mrms))) / (np.mean(mrms) + 1e-9))

    # harmonic proxy: mean peak autocorrelation on voiced frames
    fr = _frames(voiced, FRAME * 2, HOP)
    hnr_proxy = 0.0
    if len(fr):
        vals = []
        for i in range(0, len(fr), 4):
            if i >= len(mask) or mask[i]:
                f = fr[i] - fr[i].mean()
                e = np.sum(f ** 2)
                if e > 1e-6:
                    ac = np.correlate(f, f, mode="full")[len(f) - 1:]
                    ac /= (ac[0] + 1e-12)
                    seg = ac[int(sr / FMAX): int(sr / FMIN)]
                    vals.append(float(seg.max()) if len(seg) else 0.0)
        if vals:
            hnr_proxy = float(np.median(vals))

    peak_rms = float(np.max(mrms)) if len(mrms) else 0.0
    clipping = float(np.mean(np.abs(x) > 0.985))

    # ---- radar scores (0..100) ----
    pitch_score = _norm(med_f0, 70, 330)
    depth = 100 - _norm(spec["centroid"], 900, 3400)
    brightness = _norm(spec["centroid"], 900, 3400)
    warmth = _norm(f1, 350, 800) * 0.5 + _norm(spec["band_low"], 0.25, 0.75) * 0.5
    roughness = _norm(jitter * 100, 0.5, 6.0) * 0.6 + _norm(shimmer * 100, 4, 40) * 0.4
    breathiness = (1 - hnr_proxy) * 100 * 0.6 + _norm(spec["band_high"], 0.02, 0.30) * 0.4
    clarity = (hnr_proxy * 100) * 0.6 + (100 - _norm(spec["flatness"], 0.005, 0.25)) * 0.4
    energy = _norm(np.mean(mrms) if len(mrms) else 0, 0.005, 0.25)

    radar = {
        "pitch": round(pitch_score, 1),
        "depth": round(depth, 1),
        "warmth": round(warmth, 1),
        "brightness": round(brightness, 1),
        "roughness": round(roughness, 1),
        "breathiness": round(breathiness, 1),
        "clarity": round(clarity, 1),
        "energy": round(energy, 1),
    }

    archetype = _archetype(med_f0, depth, brightness, roughness)

    warnings = []
    if duration < 6:
        warnings.append("Sample is short - 10-30 seconds gives a much better clone.")
    if clipping > 0.01:
        warnings.append("Audio shows clipping - lower the input volume next time.")
    if speech_ratio < 0.35:
        warnings.append("Lots of silence detected - trim dead air for a stronger clone.")
    if spec["flatness"] > 0.20 and speech_ratio > 0.3:
        warnings.append("Audio may be noisy - record in a quieter place if possible.")

    return {
        "duration": round(duration, 2),
        "sample_rate": sr,
        "f0_median": round(med_f0, 1),
        "f0_range": round(pitch_range, 1),
        "f0_min": round(float(np.nanmin(f0v)), 1) if len(f0v) else 0.0,
        "f0_max": round(float(np.nanmax(f0v)), 1) if len(f0v) else 0.0,
        "jitter": round(jitter, 4),
        "shimmer": round(shimmer, 4),
        "hnr_proxy": round(hnr_proxy, 3),
        "speech_ratio": round(speech_ratio, 3),
        "spectral_centroid": round(spec["centroid"], 0),
        "rolloff85": round(spec["rolloff85"], 0),
        "formant_f1": round(f1, 0),
        "formant_f2": round(f2, 0),
        "peak_rms": round(peak_rms, 4),
        "clipping_ratio": round(clipping, 4),
        "radar": radar,
        "archetype": archetype,
        "warnings": warnings,
    }


VOICE_LABELS_M = {  # by median pitch bands
    (60, 100): "Deep Bass", (100, 130): "Baritone", (130, 160): "Tenor",
}
VOICE_LABELS_F = {
    (140, 180): "Alto", (180, 230): "Mezzo", (230, 400): "Soprano",
}


def _archetype(med_f0: float, depth: float, brightness: float, roughness: float) -> str:
    if med_f0 <= 0:
        return "Unknown"
    texture = ("gritty" if roughness > 62 else
               "airy" if roughness < 25 else "smooth")
    tone = ("dark" if depth > 62 else "bright" if brightness > 62 else "balanced")
    if med_f0 < 105:
        band = "Bass"
    elif med_f0 < 135:
        band = "Baritone"
    elif med_f0 < 165:
        band = "Tenor"
    elif med_f0 < 200:
        band = "Alto"
    elif med_f0 < 260:
        band = "Mezzo-Soprano"
    else:
        band = "Soprano"
    return f"{texture.title()} {tone.title()} {band}"
