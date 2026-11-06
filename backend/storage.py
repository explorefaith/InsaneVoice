"""InsaneVoice - JSON file storage for voice profiles & generation history."""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path

from config import DATA_DIR

VOICES_FILE = DATA_DIR / "voices.json"
HISTORY_FILE = DATA_DIR / "history.json"
_lock = threading.RLock()


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except Exception:
        return default


def _write(path: Path, data) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


# ---------- voices ----------

def list_voices() -> list[dict]:
    with _lock:
        return sorted(_read(VOICES_FILE, []), key=lambda v: v["created_at"], reverse=True)


def get_voice(vid: str) -> dict | None:
    with _lock:
        for v in _read(VOICES_FILE, []):
            if v["id"] == vid:
                return v
    return None


def add_voice(profile: dict) -> dict:
    with _lock:
        voices = _read(VOICES_FILE, [])
        voices.append(profile)
        _write(VOICES_FILE, voices)
    return profile


def update_voice(vid: str, patch: dict) -> dict | None:
    with _lock:
        voices = _read(VOICES_FILE, [])
        for v in voices:
            if v["id"] == vid:
                v.update(patch)
                _write(VOICES_FILE, voices)
                return v
    return None


def delete_voice(vid: str) -> dict | None:
    with _lock:
        voices = _read(VOICES_FILE, [])
        keep = [v for v in voices if v["id"] != vid]
        if len(keep) == len(voices):
            return None
        _write(VOICES_FILE, keep)
    return next((v for v in voices if v["id"] == vid), None)


# ---------- history ----------

def add_history(entry: dict) -> dict:
    with _lock:
        hist = _read(HISTORY_FILE, [])
        hist.append(entry)
        if len(hist) > 400:
            hist = hist[-400:]
        _write(HISTORY_FILE, hist)
    return entry


def list_history(limit: int = 100) -> list[dict]:
    with _lock:
        hist = _read(HISTORY_FILE, [])
    return list(reversed(hist[-limit:]))


def get_history(hid: str) -> dict | None:
    with _lock:
        for h in _read(HISTORY_FILE, []):
            if h["id"] == hid:
                return h
    return None


def delete_history(hid: str) -> dict | None:
    with _lock:
        hist = _read(HISTORY_FILE, [])
        keep = [h for h in hist if h["id"] != hid]
        if len(keep) == len(hist):
            return None
        _write(HISTORY_FILE, keep)
    return next((h for h in hist if h["id"] == hid), None)
