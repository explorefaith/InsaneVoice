"""InsaneVoice — offline speech-to-text (Vosk, 20+ languages, ~50MB models).

Models download once from alphacephei.com and live in .ivdata/models/vosk/.
Used by: Transcribe page, Dubbing Studio, voice-ownership verification.
"""
from __future__ import annotations

import json
import subprocess
import zipfile
from pathlib import Path

import config

MODELS_DIR = config.MODELS_DIR / "vosk"
MODEL_LIST_URL = "https://alphacephei.com/vosk/models/model-list.json"
BASE_URL = "https://alphacephei.com/vosk/models/"

FALLBACK_SMALL = {
    "en-us": "vosk-model-small-en-us-0.15",
    "es": "vosk-model-small-es-0.42",
    "fr": "vosk-model-small-fr-0.22",
    "zh-cn": "vosk-model-small-cn-0.22",
    "ja": "vosk-model-small-ja-0.22",
    "ko": "vosk-model-small-ko-0.22",
    "de": "vosk-model-small-de-0.15",
    "it": "vosk-model-small-it-0.22",
    "pt": "vosk-model-small-pt-0.3",
    "ru": "vosk-model-small-ru-0.22",
    "hi": "vosk-model-small-hi-0.22",
    "tr": "vosk-model-small-tr-0.3",
    "vi": "vosk-model-small-vn-0.3",
    "nl": "vosk-model-nl-samt-0.54",
}


def available() -> bool:
    try:
        import vosk  # noqa: F401
        return True
    except Exception:
        return False


def model_dir(lang: str) -> Path | None:
    if not MODELS_DIR.exists():
        return None
    for d in sorted(MODELS_DIR.iterdir()):
        if d.is_dir() and d.name.startswith("vosk-model") and (d / "conf").exists():
            if lang[:2] in d.name or (lang == "en-us" and "en-us" in d.name):
                return d
    return None


def ensure_model(lang: str = "en-us") -> Path:
    """Download the smallest model for a language if not present."""
    import urllib.request

    if m := model_dir(lang):
        return m
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    name = FALLBACK_SMALL.get(lang)
    if name is None:
        # look up the smallest model for this language from the official list
        try:
            with urllib.request.urlopen(MODEL_LIST_URL, timeout=30) as r:
                entries = json.load(r)
            cands = [e for e in entries if e.get("lang", "").startswith(lang[:2])
                     and e.get("size") and "small" in e.get("name", "")]
            if not cands:
                cands = [e for e in entries if e.get("lang", "").startswith(lang[:2])]
            if cands:
                name = min(cands, key=lambda e: e["size"])["name"]
        except Exception:
            pass
    if not name:
        raise RuntimeError(f"No vosk model found for language '{lang}'.")

    url = BASE_URL + name + ".zip"
    zpath = MODELS_DIR / (name + ".zip")
    print(f"[stt] downloading {name} ...", flush=True)
    urllib.request.urlretrieve(url, zpath)
    with zipfile.ZipFile(zpath) as z:
        z.extractall(MODELS_DIR)
    zpath.unlink(missing_ok=True)
    m = model_dir(lang)
    if not m:
        raise RuntimeError("Model extracted but not found — unexpected layout.")
    print(f"[stt] model ready: {m.name}", flush=True)
    return m


def _to_wav16k(src: Path, dst: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-i", str(src), "-ar", "16000", "-ac", "1", "-sample_fmt", "s16",
         str(dst)],
        check=True, capture_output=True, timeout=600)


def _fmt_ts(t: float) -> str:
    ms = int(round((t - int(t)) * 1000))
    s = int(t)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


def transcribe(audio_path: str | Path, lang: str = "en-us",
               progress=None) -> dict:
    """-> {text, words:[{word,start,end,conf}], segments:[{start,end,text}], srt}"""
    from vosk import Model, KaldiRecognizer, SetLogLevel

    SetLogLevel(-1)
    src = Path(audio_path)
    wav = src.with_suffix(".16k.wav")
    _to_wav16k(src, wav)

    mdir = ensure_model(lang)
    model = Model(str(mdir))
    rec = KaldiRecognizer(model, 16000)
    rec.SetWords(True)

    import wave
    words: list[dict] = []
    text_parts: list[str] = []
    with wave.open(str(wav), "rb") as wf:
        total = wf.getnframes() / wf.getframerate()
        done = 0.0
        while True:
            data = wf.readframes(8000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                part = json.loads(rec.Result())
                text_parts.append(part.get("text", ""))
                words += part.get("result", []) or []
            done += 8000 / 16000
            if progress:
                progress(min(0.99, done / max(total, 0.1)))
        final = json.loads(rec.FinalResult())
        text_parts.append(final.get("text", ""))
        words += final.get("result", []) or []

    wav.unlink(missing_ok=True)
    text = " ".join(t for t in text_parts if t).strip()

    # group words into caption segments (<= 6s or sentence-ish break)
    segments: list[dict] = []
    cur: list[dict] = []
    for w in words:
        cur.append(w)
        gap_break = (len(cur) > 1 and (w["start"] - cur[-2]["end"]) > 0.55)
        if (w["end"] - cur[0]["start"] > 6.0 or gap_break
                or w["word"].endswith((".", "?", "!"))):
            segments.append({"start": cur[0]["start"], "end": cur[-1]["end"],
                             "text": " ".join(x["word"] for x in cur)})
            cur = []
    if cur:
        segments.append({"start": cur[0]["start"], "end": cur[-1]["end"],
                         "text": " ".join(x["word"] for x in cur)})

    srt_lines = []
    for i, s in enumerate(segments, 1):
        srt_lines.append(f"{i}\n{_fmt_ts(s['start'])} --> {_fmt_ts(s['end'])}\n{s['text']}\n")

    return {"text": text,
            "words": words,
            "segments": segments,
            "srt": "\n".join(srt_lines),
            "duration": round(total, 2)}
