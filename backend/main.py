"""InsaneVoice — FastAPI backend v2.

v1: upload/record → Voice DNA → clone → generate → history
v2: + multi-language TTS, emotional/non-verbal rendering, voice changer,
      isolator, STT (vosk), ownership verification, voice design,
      dialogue pacing, Director's projects, dubbing, Agent Studio
      (provider connections + SSE pipeline), motion-graphics renderer.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import threading
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import config
import dna
import engine
import langs
import storage

sys.path.insert(0, str(config.BACKEND_DIR))

app = FastAPI(title=config.APP_NAME, version="2.0.0")


class _CorsPna(CORSMiddleware):
    """CORS + Chrome's Private/Local-Network-Access preflight header, so the
    hosted UI (insanevoice.vercel.app) may call this local engine."""

    def preflight_response(self, request_headers):
        resp = super().preflight_response(request_headers)
        resp.headers["Access-Control-Allow-Private-Network"] = "true"
        return resp


app.add_middleware(
    _CorsPna,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
                       r"|^https://insanevoice(-[\w-]+)?\.vercel\.app$"
                       r"|^https://[a-z0-9-]+\.trycloudflare\.com$",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _no_static_cache(request, call_next):
    resp = await call_next(request)
    p = request.url.path
    if p == "/" or p.startswith("/static"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp

ALLOWED_EXT = {".wav", ".mp3", ".m4a", ".ogg", ".webm", ".flac", ".opus", ".aac"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
AUDIO_MEDIA = "audio/wav"
MAX_AUDIO_MB = 30
MAX_VIDEO_MB = 600

FRONTEND_DIR = config.REPO_ROOT / "frontend"


# ---------- helpers ----------

def _ok(payload: dict, status: int = 200) -> JSONResponse:
    return JSONResponse({"ok": True, **payload}, status_code=status)


def _err(msg: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "error": msg}, status_code=status)


def _ffmpeg() -> str:
    import shutil as sh
    p = sh.which("ffmpeg")
    if not p:
        raise RuntimeError("ffmpeg not found in PATH.")
    return p


def normalize_audio(raw_path: Path, out_wav: Path, sr: int = None) -> float:
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = [_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
           "-i", str(raw_path), "-ac", "1",
           "-ar", str(sr or config.SAMPLE_RATE), str(out_wav)]
    import subprocess
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        raise RuntimeError(f"Could not decode audio: {r.stderr[-300:]}")
    import soundfile as sf
    return float(sf.info(str(out_wav)).duration)


def _save_upload(upload: UploadFile, prefix: str,
                 max_mb: int = MAX_AUDIO_MB,
                 allowed: set | None = None) -> tuple[Path, Path, float]:
    allowed = allowed if allowed is not None else ALLOWED_EXT
    ext = Path(upload.filename or "").suffix.lower() or ".webm"
    if ext not in allowed:
        raise HTTPException(400, f"Unsupported format '{ext}'.")
    uid = storage.new_id(prefix)
    raw = config.UPLOADS_DIR / f"{uid}{ext}"
    size = 0
    with raw.open("wb") as f:
        while chunk := upload.file.read(1 << 20):
            size += len(chunk)
            if size > max_mb << 20:
                f.close()
                raw.unlink(missing_ok=True)
                raise HTTPException(413, f"File larger than {max_mb}MB.")
            f.write(chunk)
    if size < 4096:
        raw.unlink(missing_ok=True)
        raise HTTPException(400, "File is too small or empty.")
    wav = config.SAMPLES_DIR / f"{uid}.wav"
    try:
        duration = normalize_audio(raw, wav)
    except Exception:
        raw.unlink(missing_ok=True)
        raise
    return raw, wav, duration


def _serve_audio(p: Path):
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type=AUDIO_MEDIA)


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
    return _err("Frontend missing.", 404)


@app.get("/api/health")
def health():
    return _ok({"service": config.APP_NAME, "version": "2.0.0"})


@app.get("/api/system")
def system():
    import platform
    import stt as stt_mod
    return _ok({
        "app": config.APP_NAME, "version": "2.0.0",
        "python": platform.python_version(),
        "models_present": config.models_present(),
        "engine": engine.status(),
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "stt": {"available": stt_mod.available(),
                "models": sorted({d.name for d in (config.MODELS_DIR / "vosk").glob("vosk-model-*")}
                                 if (config.MODELS_DIR / "vosk").exists() else [])},
        "languages": langs.all_lang_list(),
        "voices": len(storage.list_voices()),
        "data_dir": str(config.DATA_DIR),
    })


# ---------- voices (v1 surface, + lang-aware generate + emotional) ----------

@app.post("/api/analyze")
async def analyze_sample(file: UploadFile = File(...)):
    raw, wav, duration = _save_upload(file, "ana")
    try:
        report = dna.analyze(str(wav))
    except Exception as e:
        raise HTTPException(500, f"Analysis failed: {e}")
    report["sample_id"] = wav.stem
    report["sample_url"] = f"/api/audio/samples/{wav.name}"
    return _ok({"dna": report})


@app.post("/api/voices")
async def create_voice(file: UploadFile = File(...), name: str = Form(...),
                       consent: str = Form("false"), notes: str = Form(""),
                       language: str = Form("")):
    if consent.lower() != "true":
        return _err("Consent is required.", 403)
    if not config.models_present():
        return _err("Models not downloaded yet (scripts/download_models.py).", 503)
    if not (name or "").strip():
        return _err("Voice name is required.")
    raw, wav, duration = _save_upload(file, "ref")
    vid = wav.stem
    try:
        report = dna.analyze(str(wav))
        se_path = config.VOICES_DIR / f"{vid}.pth"
        engine.extract_speaker_embedding(wav, se_path)
    except Exception as e:
        raise HTTPException(500, f"Voice creation failed: {e}")
    profile = {
        "id": vid, "name": name.strip()[:60], "created_at": storage.now(),
        "sample": wav.name, "sample_url": f"/api/audio/samples/{wav.name}",
        "se_path": str(se_path), "duration": round(duration, 2),
        "consent": True, "notes": notes[:300], "dna": report, "verified": False,
        "language": (language or "other").lower(),
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


@app.post("/api/generate")
async def generate(req: dict):
    vid = (req.get("voice_id") or "").strip()
    text = (req.get("text") or "").strip()
    speed = float(req.get("speed") or 1.0)
    tau = float(req.get("tau") if req.get("tau") is not None else 0.3)
    accent = req.get("accent") or None
    lang = (req.get("lang") or "en").lower()
    emotional = bool(req.get("emotional"))
    if not vid:
        return _err("Pick a voice first.")
    if not text:
        return _err("Text is empty.")
    if not (0.5 <= speed <= 2.0) or not (0.05 <= tau <= 0.95):
        return _err("Speed/tau out of range.")
    voice = storage.get_voice(vid)
    if not voice:
        raise HTTPException(404, "Voice not found.")

    uid = storage.new_id("gen")
    out = config.OUTPUT_DIR / f"{uid}.wav"
    t0 = time.time()
    timeline = None
    try:
        if emotional:
            import emotions
            work = config.DATA_DIR / "genwork" / uid
            def speak_fn(t: str, o: Path):
                engine.generate(t, voice["se_path"], o, speed=speed,
                                tau=tau, accent=accent, lang=lang)
            res = emotions.render_emotional(text, work, speak_fn)
            shutil.copy(res["file"], out)
            timeline = {"timeline": res["timeline"], "total": res["total"],
                        "warnings": res["warnings"]}
        else:
            engine.generate(text, voice["se_path"], out, speed=speed,
                            tau=tau, accent=accent, lang=lang)
    except Exception as e:
        raise HTTPException(500, f"Generation failed: {e}")
    elapsed = round(time.time() - t0, 2)
    import soundfile as sf
    info = sf.info(str(out))
    entry = {"id": uid, "voice_id": vid, "voice_name": voice["name"],
             "text": text[:2000], "file": out.name,
             "audio_url": f"/api/audio/output/{out.name}",
             "duration": round(info.duration, 2), "elapsed": elapsed,
             "speed": speed, "tau": tau, "accent": accent, "lang": lang,
             "emotional": emotional, "timeline": timeline,
             "created_at": storage.now()}
    storage.add_history(entry)
    return _ok({"generation": entry})


# ---------- history ----------

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
             "speed": 1.0, "tau": 0.3, "accent": "en-us", "lang": "en",
             "preview": True, "created_at": storage.now()}
    storage.add_history(entry)
    return _ok({"generation": entry})


# ---------- ownership verification ----------

@app.get("/api/voices/{vid}/challenge")
def challenge(vid: str):
    import verify
    v = storage.get_voice(vid)
    if not v:
        raise HTTPException(404, "Voice not found.")
    words = verify.make_challenge()
    storage.update_voice(vid, {"challenge": " ".join(words)})
    return _ok({"words": words,
                "instruction": "Record yourself reading these words naturally, "
                               "then submit the recording."})


@app.post("/api/voices/{vid}/verify")
async def verify_voice(vid: str, file: UploadFile = File(...)):
    import verify
    v = storage.get_voice(vid)
    if not v:
        raise HTTPException(404, "Voice not found.")
    raw, wav, _ = _save_upload(file, "vrf")
    res = verify.check_challenge(v["dna"], str(wav))
    if res["passed"]:
        storage.update_voice(vid, {"verified": True, "verified_at": storage.now()})
    return _ok({"verification": res, "voice": storage.get_voice(vid)})


# ---------- voice changer (audio-to-audio performance transfer) ----------

@app.post("/api/changer")
async def voice_changer(file: UploadFile = File(...), voice_id: str = Form(...),
                        tau: float = Form(0.3)):
    if not config.models_present():
        return _err("Models not downloaded yet.", 503)
    voice = storage.get_voice(voice_id)
    if not voice:
        raise HTTPException(404, "Voice not found.")
    raw, wav, duration = _save_upload(file, "chg")
    uid = storage.new_id("chg")
    out = config.OUTPUT_DIR / f"{uid}.wav"
    t0 = time.time()
    try:
        engine.convert_audio(wav, voice["se_path"], out, tau=float(tau))
    except Exception as e:
        raise HTTPException(500, f"Conversion failed: {e}")
    import soundfile as sf
    info = sf.info(str(out))
    entry = {"id": uid, "voice_id": voice_id, "voice_name": voice["name"],
             "text": f"[voice changer] {Path(file.filename or '').name}",
             "file": out.name, "audio_url": f"/api/audio/output/{out.name}",
             "duration": round(info.duration, 2),
             "elapsed": round(time.time() - t0, 2), "tau": tau,
             "preview": True, "created_at": storage.now()}
    storage.add_history(entry)
    return _ok({"conversion": entry})


# ---------- isolator ----------

@app.post("/api/isolate")
async def isolate(file: UploadFile = File(...)):
    raw, wav, duration = _save_upload(file, "iso", max_mb=MAX_AUDIO_MB)
    uid = storage.new_id("iso")
    out = config.OUTPUT_DIR / f"{uid}_clean.wav"
    import subprocess
    r = subprocess.run(
        [_ffmpeg(), "-y", "-loglevel", "error", "-i", str(wav),
         "-af", "afftdn=nr=12:nf=-25,highpass=f=70,lowpass=f=12000,"
                "speechnorm=e=6.25:r=0.00001:l=1", "-ar", "22050", "-ac", "1",
         str(out)],
        capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        raise HTTPException(500, f"Isolation failed: {r.stderr[-200:]}")
    import soundfile as sf
    return _ok({"isolated": {
        "id": uid, "file": out.name, "url": f"/api/audio/output/{out.name}",
        "duration": round(sf.info(str(out)).duration, 2),
        "original_url": f"/api/audio/samples/{wav.name}"}})


# ---------- STT ----------

@app.get("/api/stt/status")
def stt_status():
    import stt as stt_mod
    return _ok({"available": stt_mod.available(),
                "models": sorted({d.name for d in (config.MODELS_DIR / "vosk").glob("vosk-model-*")}
                                 if (config.MODELS_DIR / "vosk").exists() else [])})


@app.post("/api/transcribe")
async def transcribe(file: UploadFile = File(...), lang: str = Form("en-us")):
    import stt as stt_mod
    if not stt_mod.available():
        return _err("vosk is not installed in this environment.", 503)
    raw, wav, duration = _save_upload(file, "trn", max_mb=200)
    try:
        res = stt_mod.transcribe(wav, lang=lang)
    except Exception as e:
        raise HTTPException(500, f"Transcription failed: {e}")
    res["audio_url"] = f"/api/audio/samples/{wav.name}"
    return _ok({"transcript": res})


# ---------- voice design ----------

@app.post("/api/design/preview")
async def design_preview(req: dict):
    import voice_design as vd
    desc = req.get("description") or ""
    targets = vd.parse_description(desc)
    for k in ("f0", "warm", "bright", "rough", "breathy", "tempo"):
        if req.get(k) is not None:
            targets[k] = req[k]
    accent = targets.get("accent") or "en-us"
    sid = storage.new_id("dsn")
    work = config.DATA_DIR / "design" / sid
    res = vd.design(_base_speak_factory(accent), work, targets)
    import soundfile as sf
    dur = sf.info(str(res["file"])).duration
    return _ok({"session": sid, "targets": targets, "report": res["report"],
                "audio_url": f"/api/design/audio/{sid}/{res['file'].name}",
                "duration": round(dur, 2)})


def _base_speak_factory(accent: str):
    def speak(text: str, out: Path):
        engine.ensure_loaded(block=True)
        with engine._lock:
            engine._load_tts("en")
            tts = engine._tts_pool["en"]
            spk_ids = tts.hps.data.spk2id
            spk = ("EN-BR" if accent == "en-br" else "EN-US")
            spk = spk if spk in spk_ids else list(spk_ids)[0]
            tts.tts_to_file(text, spk_ids[spk], str(out), speed=1.0)
    return speak


@app.get("/api/design/audio/{sid}/{name}")
def design_audio(sid: str, name: str):
    p = (config.DATA_DIR / "design" / sid / Path(name).name)
    return _serve_audio(p)


@app.post("/api/design/save")
async def design_save(req: dict):
    """Save a designed voice: {session, name, consent, notes}"""
    sid = req.get("session") or ""
    d = (config.DATA_DIR / "design" / Path(sid).name)
    wav = None
    for cand in sorted(d.glob("design_pass*.wav")) + sorted(d.glob("design_base.wav")):
        wav = cand            # last pass wins
    if not wav or not wav.exists():
        raise HTTPException(404, "Design session not found — preview again.")
    if not req.get("consent"):
        return _err("Consent is required.", 403)
    name = (req.get("name") or "Designed voice").strip()[:60]
    vid = storage.new_id("ref")
    import shutil
    final_wav = config.SAMPLES_DIR / f"{vid}.wav"
    shutil.copy(wav, final_wav)
    report = dna.analyze(str(final_wav))
    se_path = config.VOICES_DIR / f"{vid}.pth"
    engine.extract_speaker_embedding(final_wav, se_path)
    profile = {"id": vid, "name": name, "created_at": storage.now(),
               "sample": final_wav.name,
               "sample_url": f"/api/audio/samples/{final_wav.name}",
               "se_path": str(se_path), "duration": report["duration"],
               "consent": True, "notes": (req.get("notes") or "")[:300],
               "dna": report, "verified": True, "designed": True,
               "design_desc": (req.get("description") or "")[:200]}
    storage.add_voice(profile)
    return _ok({"voice": profile}, 201)


# ---------- dialogue (multi-speaker contextual pacing) ----------

@app.post("/api/dialogue")
async def dialogue(req: dict):
    import pacing
    import soundfile as sf
    import numpy as np

    lines = req.get("lines") or []
    lines = [l for l in lines if (l.get("text") or "").strip()]
    if len(lines) < 1:
        return _err("Need at least one line.")
    planned = pacing.plan_pauses(lines)
    parts = []
    timeline = []
    uid = storage.new_id("dlg")
    work = config.DATA_DIR / "genwork" / uid
    work.mkdir(parents=True, exist_ok=True)
    for i, ln in enumerate(planned):
        gap = float(ln.get("gap_before", 0.35))
        if gap > 0:
            parts.append(("gap", gap))
        voice = storage.get_voice(ln.get("voice_id") or "")
        if not voice:
            raise HTTPException(404, f"Line {i + 1}: voice not found.")
        wav = work / f"line{i:02d}.wav"
        engine.generate(ln["text"], voice["se_path"], wav,
                        speed=float(ln.get("speed", 1.0)),
                        tau=float(ln.get("tau", 0.3)),
                        accent=ln.get("accent"), lang=ln.get("lang", "en"))
        parts.append(("wav", wav))
        timeline.append({"text": ln["text"], "voice": voice["name"],
                         "gap_before": gap})

    final = config.OUTPUT_DIR / f"{uid}.wav"
    pieces = []
    for kind, v in parts:
        if kind == "gap":
            pieces.append(np.zeros(int(v * 22050), dtype=np.float32))
        else:
            x, sr = sf.read(str(v), dtype="float32", always_2d=True)
            if sr != 22050:
                import subprocess
                tmp = v.with_suffix(".r.wav")
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(v),
                                "-ar", "22050", "-ac", "1", str(tmp)], check=True)
                x, _ = sf.read(str(tmp), dtype="float32", always_2d=True)
                tmp.unlink(missing_ok=True)
            pieces.append(x.mean(axis=1))
    sf.write(str(final), np.concatenate(pieces).astype(np.float32), 22050)
    info = sf.info(str(final))
    entry = {"id": uid, "voice_id": "dialogue", "voice_name": "Dialogue",
             "text": " · ".join(l["text"][:40] for l in timeline),
             "file": final.name, "audio_url": f"/api/audio/output/{final.name}",
             "duration": round(info.duration, 2), "elapsed": None,
             "timeline": timeline, "dialogue": True,
             "created_at": storage.now()}
    storage.add_history(entry)
    return _ok({"dialogue": entry})


# ---------- director's projects ----------

import projects  # noqa: E402

@app.post("/api/projects")
def projects_create(req: dict):
    try:
        proj = projects.create(req.get("title") or "Untitled",
                               req.get("voice_id") or "",
                               req.get("script") or "",
                               lang=(req.get("lang") or "en"),
                               accent=req.get("accent"),
                               speed=float(req.get("speed") or 1.0),
                               tau=float(req.get("tau") if req.get("tau") is not None else 0.3))
        return _ok({"project": proj}, 201)
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/projects")
def projects_list():
    return _ok({"projects": projects.list_projects()})


@app.get("/api/projects/{pid}")
def projects_get(pid: str):
    p = projects.get(pid)
    if not p:
        raise HTTPException(404, "Project not found.")
    return _ok({"project": p})


@app.delete("/api/projects/{pid}")
def projects_delete(pid: str):
    return _ok({"deleted": projects.delete(pid)})


@app.post("/api/projects/{pid}/chunks")
def projects_add_chunk(pid: str, req: dict):
    c = projects.add_chunk(pid, req.get("text") or "", req.get("after"))
    if not c:
        raise HTTPException(404, "Project not found.")
    return _ok({"chunk": c}, 201)


@app.patch("/api/projects/{pid}/chunks/{cid}")
def projects_patch_chunk(pid: str, cid: str, req: dict):
    c = projects.update_chunk(pid, cid, req)
    if not c:
        raise HTTPException(404, "Chunk not found.")
    return _ok({"chunk": c})


@app.delete("/api/projects/{pid}/chunks/{cid}")
def projects_del_chunk(pid: str, cid: str):
    return _ok({"deleted": projects.delete_chunk(pid, cid)})


@app.post("/api/projects/{pid}/chunks/{cid}/takes")
def projects_gen_take(pid: str, cid: str, req: dict = None):
    req = req or {}
    try:
        take = projects.gen_take(pid, cid, variant=int(req.get("variant") or 0))
        return _ok({"take": take}, 201)
    except Exception as e:
        raise HTTPException(500, str(e))


@app.delete("/api/projects/{pid}/chunks/{cid}/takes/{tid}")
def projects_del_take(pid: str, cid: str, tid: str):
    return _ok({"deleted": projects.delete_take(pid, cid, tid)})


@app.post("/api/projects/{pid}/export")
def projects_export(pid: str, req: dict = None):
    req = req or {}
    try:
        res = projects.export_project(pid, gap=float(req.get("gap") or 0.45),
                                      isolate=bool(req.get("isolate")),
                                      fmt=req.get("fmt") or "wav")
        return _ok({"export": res})
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/projects/{pid}/audio/{name}")
def project_audio(pid: str, name: str):
    p = (config.DATA_DIR / "projects" / Path(pid).name / Path(name).name)
    return _serve_audio(p)


# ---------- dubbing ----------

@app.post("/api/dubbing/ingest")
async def dubbing_ingest(file: UploadFile = File(...), lang: str = Form("en-us")):
    import dubbing
    import stt as stt_mod
    if not stt_mod.available():
        return _err("vosk not available — install it for transcription.", 503)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in (".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v",
                   ".wav", ".mp3", ".m4a"):
        raise HTTPException(400, "Upload a video or audio file.")
    uid = storage.new_id("dubsrc")
    raw = config.UPLOADS_DIR / f"{uid}{ext}"
    size = 0
    with raw.open("wb") as f:
        while chunk := file.file.read(1 << 20):
            size += len(chunk)
            if size > MAX_VIDEO_MB << 20:
                f.close()
                raw.unlink(missing_ok=True)
                raise HTTPException(413, f"File larger than {MAX_VIDEO_MB}MB.")
            f.write(chunk)
    try:
        res = dubbing.ingest(raw, lang=lang)
    except Exception as e:
        raise HTTPException(500, f"Ingest failed: {e}")
    state = config.DATA_DIR / "dubbing" / res["id"] / "state.json"
    state.write_text(json.dumps({**res, "media": {"video": str(raw), "audio": res["media"]["audio"]}},
                                ensure_ascii=False), encoding="utf-8")
    res["media"]["video_url"] = f"/api/dubbing/{res['id']}/media"
    return _ok({"dub": res})


@app.get("/api/dubbing/{did}/media")
def dubbing_media(did: str):
    p = config.DATA_DIR / "dubbing" / Path(did).name / "source.wav"
    return _serve_audio(p)


@app.post("/api/dubbing/{did}/revoice")
async def dubbing_revoice(did: str, req: dict):
    import dubbing
    state = config.DATA_DIR / "dubbing" / Path(did).name / "state.json"
    if not state.exists():
        raise HTTPException(404, "Dubbing session not found.")
    dub = json.loads(state.read_text(encoding="utf-8"))
    try:
        res = dubbing.revoice(dub, req.get("assignments") or [])
    except Exception as e:
        raise HTTPException(500, f"Revoice failed: {e}")
    return _ok(res)


# ---------- DubHub: cross-language dubbing ----------

@app.get("/api/dubhub/langs")
def dubhub_langs():
    """What DubHub can do: transcription sources (vosk) x dub targets."""
    import stt as stt_mod
    import translation
    return _ok({
        "sources": sorted(stt_mod.FALLBACK_SMALL.keys()),
        "targets": sorted(translation.supported().keys()),
    })


@app.post("/api/dubhub/{did}/translate")
async def dubhub_translate(did: str, req: dict):
    """Translate the transcribed segments into the target language (local
    NLLB-200; weights download once on first use)."""
    state = config.DATA_DIR / "dubbing" / Path(did).name / "state.json"
    if not state.exists():
        raise HTTPException(404, "Dubbing session not found.")
    dub = json.loads(state.read_text(encoding="utf-8"))
    target = (req.get("target") or "en").lower().strip()
    src = dub.get("source_lang", "en-us")
    src_code = src.split("-")[0]
    lines = [seg["text"] for seg in dub.get("segments", [])]
    if not lines:
        raise HTTPException(400, "No transcribed segments to translate.")
    try:
        import translation
        out = translation.translate_lines(lines, src_code, target)
    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        raise HTTPException(500, f"Translation failed: {e}")
    dub["translated"] = out
    dub["target_lang"] = target
    state.write_text(json.dumps(dub, ensure_ascii=False), encoding="utf-8")
    return _ok({"lines": out, "target": target, "count": len(out)})


@app.post("/api/dubhub/{did}/render")
async def dubhub_render(did: str, req: dict):
    """Re-voice the translated segments in the target language and mux."""
    import dubbing
    state = config.DATA_DIR / "dubbing" / Path(did).name / "state.json"
    if not state.exists():
        raise HTTPException(404, "Dubbing session not found.")
    dub = json.loads(state.read_text(encoding="utf-8"))
    translated = dub.get("translated") or []
    if not translated:
        return _err("Translate first — there is no translated text to dub.")
    target = dub.get("target_lang", "en")
    voice_id = (req.get("voice_id") or "").strip()
    if not voice_id:
        return _err("Pick a voice to dub with.")
    assignments = []
    for i, seg in enumerate(dub.get("segments", [])):
        text = (translated[i] if i < len(translated) else "").strip()
        if not text:
            continue
        assignments.append({"index": i, "voice_id": voice_id, "text": text,
                            "lang": target, "tau": req.get("tau", 0.3),
                            "speed": req.get("speed", 1.0)})
    if not assignments:
        return _err("Every translated line is empty.")
    try:
        res = dubbing.revoice(dub, assignments)
    except Exception as e:
        raise HTTPException(500, f"Dub render failed: {e}")
    return _ok(res)


# ---------- agent studio ----------

import agents  # noqa: E402

@app.get("/api/connections")
def connections_get():
    return _ok({"connections": agents.masked_conns()})


@app.post("/api/connections")
async def connections_post(req: dict):
    merged = agents.save_conns(req.get("connections") or {})
    return _ok({"connections": agents.masked_conns()})


@app.post("/api/connections/test")
async def connections_test(req: dict):
    return _ok({"test": agents.test_provider(req.get("kind") or "text")})


@app.post("/api/agent/upload")
async def agent_upload(file: UploadFile = File(...)):
    """Store an attachment for the Agent Studio; returns its server path."""
    ext = Path(file.filename or "").suffix.lower()
    allowed = {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".webm", ".mkv"}
    if ext not in allowed:
        raise HTTPException(400, f"Attachment type '{ext}' not supported.")
    uid = storage.new_id("att")
    p = config.UPLOADS_DIR / f"{uid}{ext}"
    size = 0
    with p.open("wb") as f:
        while chunk := file.file.read(1 << 20):
            size += len(chunk)
            if size > MAX_VIDEO_MB << 20:
                f.close()
                p.unlink(missing_ok=True)
                raise HTTPException(413, f"Attachment larger than {MAX_VIDEO_MB}MB.")
            f.write(chunk)
    return _ok({"path": str(p), "name": file.filename, "size": size})


@app.post("/api/agent/start")
async def agent_start(req: dict):
    prompt = (req.get("prompt") or "").strip()
    if not prompt:
        return _err("Prompt is empty.")
    if not req.get("voice_id") and req.get("audio_source") != "provider":
        return _err("Pick a voice (or connect an audio provider).")
    atts = req.get("attachments") or []
    spec = {"prompt": prompt,
            "duration": float(req.get("duration") or 60),
            "voice_id": req.get("voice_id"),
            "audio_source": req.get("audio_source") or "local",
            "fit": req.get("fit") or "natural",
            "confirm": bool(req.get("confirm", True)),
            "attachments": atts}
    return _ok({"job": agents.start_job(spec)}, 201)


@app.get("/api/agent/jobs")
def agent_jobs():
    with agents.JOBS_LOCK:
        return _ok({"jobs": [j.snapshot() for j in agents.JOBS.values()]})


@app.get("/api/agent/{jid}/events")
def agent_events(jid: str):
    job = agents.get_job(jid)
    if not job:
        raise HTTPException(404, "Unknown job.")

    def gen():
        import queue as q
        while True:
            try:
                ev = job.q.get(timeout=1.0)
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                if ev.get("type") in ("done", "error"):
                    while True:
                        try:
                            ev2 = job.q.get_nowait()
                            yield f"data: {json.dumps(ev2, ensure_ascii=False)}\n\n"
                        except q.Empty:
                            break
                    return
            except q.Empty:
                yield ": ping\n\n"
                if job.state in ("done", "error") and job.q.empty():
                    return

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@app.post("/api/agent/{jid}/confirm")
async def agent_confirm(jid: str, req: dict = None):
    req = req or {}
    try:
        snap = agents.confirm_job(jid, payload=req.get("payload"),
                                  cancel=bool(req.get("cancel")))
        return _ok({"job": snap})
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/agent/video/{name}")
def agent_video(name: str, request: Request):
    p = (config.OUTPUT_DIR / Path(name).name)
    if not p.exists():
        raise HTTPException(404)
    size = p.stat().st_size
    rng = request.headers.get("range")
    if rng:
        m = re.search(r"bytes=(\d+)-(\d*)", rng)
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else size - 1
        end = min(end, size - 1)
        def it():
            with open(p, "rb") as f:
                f.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk = f.read(min(1 << 16, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk
        return StreamingResponse(it(), status_code=206, media_type="video/mp4",
                                 headers={"Content-Range": f"bytes {start}-{end}/{size}",
                                          "Accept-Ranges": "bytes"})
    return FileResponse(p, media_type="video/mp4")


# ---------- audio & static ----------

@app.get("/api/audio/{kind}/{name}")
def audio(kind: str, name: str):
    base = {"samples": config.SAMPLES_DIR, "output": config.OUTPUT_DIR}.get(kind)
    if base is None:
        raise HTTPException(404)
    p = (base / Path(name).name).resolve()
    if not str(p).startswith(str(base.resolve())) or not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type=AUDIO_MEDIA)


# ---------- cartoon studio ----------

import cartoon  # noqa: E402


def _client_id(request: Request) -> str:
    return request.headers.get("x-iv-client-id") or (request.client.host if request.client else "anon")


@app.get("/api/cartoon/quota")
def cartoon_quota(request: Request):
    cid = _client_id(request)
    active = cartoon.active_job_for(cid)
    return _ok({"quota": cartoon.quota_for(cid), "active": active,
                "configured": cartoon.PROVIDERS_FILE.exists()})


@app.post("/api/cartoon")
def cartoon_start(request: Request, req: dict):
    cid = _client_id(request)
    try:
        job = cartoon.start_job(cid, (req or {}).get("idea") or "",
                                (req or {}).get("mode") or "motion",
                                (req or {}).get("lang") or "en",
                                (req or {}).get("cast") or "")
    except PermissionError as e:
        return _err(str(e), 403)
    except RuntimeError as e:
        return _err(str(e), 409)
    except Exception as e:  # noqa: BLE001
        return _err(f"cartoon generation unavailable: {e}", 500)
    return _ok({"job": job}, 201)


@app.get("/api/cartoon/library")
def cartoon_library():
    return _ok({"videos": cartoon.library()})


@app.get("/api/cartoon/gallery")
def cartoon_gallery():
    vids = cartoon.gallery()
    for v in vids:
        v["thumb"] = f"/api/cartoon/{v['id']}/still/1"
    return _ok({"videos": vids})


@app.get("/api/admin/stats")
def admin_stats():
    return _ok(cartoon.admin_stats())


@app.get("/api/cartoon/{jid}/still/{scene}")
def cartoon_still(jid: str, scene: int):
    p = cartoon.job_still(jid, scene)
    if not p:
        raise HTTPException(404)
    return FileResponse(p, media_type="image/jpeg")


@app.get("/api/cartoon/{jid}")
def cartoon_job(jid: str):
    job = cartoon.get_job(jid)
    if not job:
        raise HTTPException(404)
    return _ok({"job": job, "stills": cartoon.job_stills(jid)})


@app.post("/api/cartoon/{jid}/reroll")
def cartoon_reroll(jid: str, req: dict):
    try:
        r = cartoon.reroll_scene(jid, int((req or {}).get("scene", 1)), cartoon._providers())
        return _ok({"reroll": r})
    except (RuntimeError, ValueError) as e:
        return _err(str(e), 400)


@app.post("/api/cartoon/{jid}/export")
def cartoon_export(jid: str, req: dict):
    p = cartoon.job_video(jid)
    if not p:
        raise HTTPException(404)
    kind = (req or {}).get("kind", "shorts")
    d = p.parent
    import subprocess as sp
    try:
        if kind == "shorts":
            out = d / "shorts.mp4"
            if not out.exists():
                sp.run(["ffmpeg", "-y", "-v", "error", "-i", str(p),
                        "-vf", "scale=-2:1920,crop=1080:1920",
                        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                        "-c:a", "copy", str(out)], check=True, timeout=600)
            media = "video/mp4"
        elif kind == "smooth":
            out = d / "smooth60.mp4"
            if not out.exists():
                sp.run(["ffmpeg", "-y", "-v", "error", "-i", str(p),
                        "-vf", "minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:vsbmc=1",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
                        "-c:a", "copy", str(out)], check=True, timeout=1800)
            media = "video/mp4"
        elif kind == "thumb":
            out = d / "thumb.jpg"
            if not out.exists():
                title = (cartoon.get_job(jid) or {}).get("title") or "InsaneVoice"
                mid = str((cartoon.get_job(jid) or {}).get("duration") or 30) .split(".")[0]
                safe = title.replace(":", "").replace("'", "").replace('"', "")
                sp.run(["ffmpeg", "-y", "-v", "error", "-ss", str(max(1, int(mid) // 2)),
                        "-i", str(p), "-frames:v", "1",
                        "-vf", f"scale=1280:720,drawtext=fontfile={cartoon.FONT}:text={safe}:fontsize=56:fontcolor=white:borderw=5:bordercolor=black@0.7:x=(w-text_w)/2:y=40",
                        "-q:v", "3", str(out)], check=True, timeout=120)
            media = "image/jpeg"
        else:
            raise HTTPException(400)
    except sp.TimeoutExpired:
        return _err("export took too long — try again", 504)
    return FileResponse(out, media_type=media, filename=out.name)


@app.get("/api/cartoon/{jid}/video")
def cartoon_video(jid: str, request: Request):
    p = cartoon.job_video(jid)
    if not p:
        raise HTTPException(404)
    size = p.stat().st_size
    rng = request.headers.get("range")
    if rng:
        m = re.search(r"bytes=(\d+)-(\d*)", rng)
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else size - 1
        end = min(end, size - 1)
        def it():
            with open(p, "rb") as f:
                f.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk = f.read(min(1 << 16, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk
        return StreamingResponse(it(), status_code=206, media_type="video/mp4",
                                 headers={"Content-Range": f"bytes {start}-{end}/{size}",
                                          "Accept-Ranges": "bytes"})
    return FileResponse(p, media_type="video/mp4")


app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8177)
