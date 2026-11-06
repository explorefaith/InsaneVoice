"""InsaneVoice - FastAPI backend.

Run:  python -m uvicorn main:app --host 127.0.0.1 --port 8177  (from backend/)
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

import config
import dna
import engine
import storage

sys.path.insert(0, str(config.BACKEND_DIR))

app = FastAPI(title=config.APP_NAME, version=config.VERSION)

ALLOWED_EXT = {".wav", ".mp3", ".m4a", ".ogg", ".webm", ".flac", ".opus", ".aac"}
AUDIO_MEDIA = "audio/wav"

FRONTEND_DIR = config.REPO_ROOT / "frontend"


# ---------- helpers ----------

def _ok(payload: dict, status: int = 200) -> JSONResponse:
    return JSONResponse({"ok": True, **payload}, status_code=status)


def _err(msg: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "error": msg}, status_code=status)


def _ffmpeg() -> str:
    p = shutil.which("ffmpeg")
    if not p:
        raise RuntimeError("ffmpeg not found in PATH. Install it, then restart InsaneVoice.")
    return p


def normalize_audio(raw_path: Path, out_wav: Path) -> float:
    """Any input -> 22050Hz mono wav. Returns duration seconds."""
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = [_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
           "-i", str(raw_path), "-ac", "1", "-ar", str(config.SAMPLE_RATE),
           str(out_wav)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"Could not decode audio: {r.stderr[-300:]}")
    import soundfile as sf
    info = sf.info(str(out_wav))
    return float(info.duration)


def _save_upload(upload: UploadFile, prefix: str) -> tuple[Path, Path, float]:
    ext = Path(upload.filename or "").suffix.lower() or ".webm"
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"Unsupported audio format '{ext}'. "
                                 f"Allowed: {', '.join(sorted(ALLOWED_EXT))}")
    uid = storage.new_id(prefix)
    raw = config.UPLOADS_DIR / f"{uid}{ext}"
    size = 0
    with raw.open("wb") as f:
        while chunk := upload.file.read(1 << 20):
            size += len(chunk)
            if size > config.MAX_UPLOAD_MB << 20:
                f.close()
                raw.unlink(missing_ok=True)
                raise HTTPException(413, f"File larger than {config.MAX_UPLOAD_MB}MB.")
            f.write(chunk)
    if size < 4096:
        raw.unlink(missing_ok=True)
        raise HTTPException(400, "Recording/file is too small or empty.")
    wav = config.SAMPLES_DIR / f"{uid}.wav"
    try:
        duration = normalize_audio(raw, wav)
    except Exception:
        raw.unlink(missing_ok=True)
        raise
    return raw, wav, duration


@app.on_event("startup")
def _startup() -> None:
    config.ensure_dirs()
    if config.models_present():
        threading.Timer(1.5, engine.warmup_async).start()


# ---------- pages ----------

@app.get("/")
def index():
    idx = FRONTEND_DIR / "index.html"
    if idx.exists():
        return FileResponse(idx)
    return _err("Frontend not built yet - see frontend/", 404)


@app.get("/api/health")
def health():
    return _ok({"service": config.APP_NAME, "version": config.VERSION})


@app.get("/api/system")
def system():
    import platform
    return _ok({
        "app": config.APP_NAME,
        "version": config.VERSION,
        "python": platform.python_version(),
        "models_present": config.models_present(),
        "engine": engine.status(),
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "voices": len(storage.list_voices()),
        "data_dir": str(config.DATA_DIR),
    })


# ---------- voice intake ----------

@app.post("/api/analyze")
async def analyze_sample(file: UploadFile = File(...)):
    """Upload/record -> normalize -> Voice DNA report (no voice saved)."""
    raw, wav, duration = _save_upload(file, "ana")
    try:
        report = dna.analyze(str(wav))
    except Exception as e:
        raise HTTPException(500, f"Analysis failed: {e}")
    report["sample_id"] = wav.stem
    report["sample_url"] = f"/api/audio/samples/{wav.name}"
    return _ok({"dna": report})


@app.post("/api/voices")
async def create_voice(
    file: UploadFile = File(...),
    name: str = Form(...),
    consent: str = Form("false"),
    notes: str = Form(""),
):
    """Analyze + extract speaker embedding -> saved voice profile."""
    if consent.lower() != "true":
        return _err("Consent is required: you must own this voice or have "
                    "explicit permission to clone it.", 403)
    if not config.models_present():
        return _err("Models not downloaded yet. Run scripts/download_models.py "
                    "first (see README).", 503)
    if not (name or "").strip():
        return _err("Voice name is required.")
    raw, wav, duration = _save_upload(file, "ref")
    vid = wav.stem
    try:
        report = dna.analyze(str(wav))
        se_path = config.VOICES_DIR / f"{vid}.pth"
        engine.extract_speaker_embedding(wav, se_path)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Voice creation failed: {e}")
    profile = {
        "id": vid,
        "name": name.strip()[:60],
        "created_at": storage.now(),
        "sample": wav.name,
        "sample_url": f"/api/audio/samples/{wav.name}",
        "se_path": str(se_path),
        "duration": round(duration, 2),
        "consent": True,
        "notes": notes[:300],
        "dna": report,
    }
    storage.add_voice(profile)
    return _ok({"voice": profile}, 201)


@app.get("/api/voices")
def list_voices():
    return _ok({"voices": storage.list_voices()})


@app.get("/api/voices/{vid}")
def get_voice(vid: str):
    v = storage.get_voice(vid)
    if not v:
        raise HTTPException(404, "Voice not found.")
    return _ok({"voice": v})


@app.delete("/api/voices/{vid}")
def delete_voice(vid: str):
    v = storage.delete_voice(vid)
    if not v:
        raise HTTPException(404, "Voice not found.")
    for p in (config.VOICES_DIR / f"{vid}.pth", config.SAMPLES_DIR / f"{vid}.wav"):
        Path(p).unlink(missing_ok=True)
    return _ok({"deleted": vid})


# ---------- generation ----------

@app.post("/api/generate")
async def generate(req: dict):
    vid = (req.get("voice_id") or "").strip()
    text = (req.get("text") or "").strip()
    speed = float(req.get("speed") or 1.0)
    tau = float(req.get("tau") if req.get("tau") is not None else 0.3)
    accent = (req.get("accent") or "en-us").lower()
    if not vid:
        return _err("Pick a voice first.")
    if not text:
        return _err("Text is empty.")
    if not (0.5 <= speed <= 2.0):
        return _err("Speed must be between 0.5 and 2.0.")
    if not (0.05 <= tau <= 0.95):
        return _err("Clone strength must be between 0.05 and 0.95.")
    voice = storage.get_voice(vid)
    if not voice:
        raise HTTPException(404, "Voice not found.")

    uid = storage.new_id("gen")
    out = config.OUTPUT_DIR / f"{uid}.wav"
    t0 = time.time()
    try:
        engine.generate(text, voice["se_path"], out, speed=speed, tau=tau, accent=accent)
    except Exception as e:
        raise HTTPException(500, f"Generation failed: {e}")
    elapsed = round(time.time() - t0, 2)
    import soundfile as sf
    info = sf.info(str(out))
    entry = {
        "id": uid,
        "voice_id": vid,
        "voice_name": voice["name"],
        "text": text[:2000],
        "file": out.name,
        "audio_url": f"/api/audio/output/{out.name}",
        "duration": round(info.duration, 2),
        "elapsed": elapsed,
        "speed": speed,
        "tau": tau,
        "accent": accent,
        "created_at": storage.now(),
    }
    storage.add_history(entry)
    return _ok({"generation": entry})


@app.post("/api/voices/{vid}/preview")
async def preview_voice(vid: str):
    voice = storage.get_voice(vid)
    if not voice:
        raise HTTPException(404, "Voice not found.")
    text = (f"Hi, this is {voice['name']}. My voice is now cloned by InsaneVoice, "
            f"and everything you hear is generated on this machine, completely free.")
    uid = storage.new_id("gen")
    out = config.OUTPUT_DIR / f"{uid}.wav"
    try:
        engine.generate(text, voice["se_path"], out)
    except Exception as e:
        raise HTTPException(500, f"Preview failed: {e}")
    import soundfile as sf
    info = sf.info(str(out))
    entry = {"id": uid, "voice_id": vid, "voice_name": voice["name"], "text": text,
             "file": out.name, "audio_url": f"/api/audio/output/{out.name}",
             "duration": round(info.duration, 2), "elapsed": None,
             "speed": 1.0, "tau": 0.3, "accent": "en-us",
             "created_at": storage.now(), "preview": True}
    storage.add_history(entry)
    return _ok({"generation": entry})


# ---------- history & files ----------

@app.get("/api/history")
def history(limit: int = 100):
    return _ok({"history": storage.list_history(min(limit, 400))})


@app.delete("/api/history/{hid}")
def delete_history(hid: str):
    h = storage.delete_history(hid)
    if not h:
        raise HTTPException(404, "History item not found.")
    Path(config.OUTPUT_DIR / h["file"]).unlink(missing_ok=True)
    return _ok({"deleted": hid})


@app.get("/api/audio/{kind}/{name}")
def audio(kind: str, name: str):
    base = {"samples": config.SAMPLES_DIR, "output": config.OUTPUT_DIR}.get(kind)
    if base is None:
        raise HTTPException(404)
    p = (base / Path(name).name).resolve()
    if not str(p).startswith(str(base.resolve())) or not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type=AUDIO_MEDIA)


app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8177)
