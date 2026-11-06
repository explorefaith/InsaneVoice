"""InsaneVoice — Agent Studio.

One prompt in, a finished narrated video out:

    script (text models, failover across ids)
      -> [confirmation gate]
    plan (scene timings fitted to the target duration)
    attachments (optional; needs a vision-capable text model)
    audio (local cloned voice, or a connected audio provider)
      -> [confirmation gate]
    visuals (built-in motion engine; optional image/video providers)
    render (ffmpeg) -> mp4

Everything streams feedback over SSE so the user always knows exactly
which stage is running and what was produced. API keys stay on disk.
"""
from __future__ import annotations

import base64
import json
import queue
import re
import threading
import time
import uuid
from pathlib import Path

import requests

import config
import engine
import motion
from storage import new_id, now

CONN_FILE = config.DATA_DIR / "connections.json"
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.RLock()

VIDEO_MIME = "video/mp4"


# ---------------- connections ----------------

DEFAULT_CONNS = {
    "text": {"base_url": "", "api_key": "", "models": [], "vision": False},
    "audio": {"base_url": "", "api_key": "", "models": [], "voice": ""},
    "visual": {"base_url": "", "api_key": "", "models": []},
}


def load_conns() -> dict:
    try:
        data = json.loads(CONN_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    merged = {k: {**DEFAULT_CONNS.get(k, {}), **(data.get(k) or {})} for k in DEFAULT_CONNS}
    return merged


def save_conns(data: dict) -> dict:
    old = load_conns()
    merged = {}
    for k, d in DEFAULT_CONNS.items():
        inc = dict(data.get(k) or {})
        # an empty api_key means "keep the saved one" (masked GET hides it)
        if not (inc.get("api_key") or "").strip():
            inc["api_key"] = old.get(k, {}).get("api_key", "")
        merged[k] = {**d, **inc}
    CONN_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONN_FILE.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
    return merged


def masked_conns() -> dict:
    c = load_conns()
    for k, v in c.items():
        key = v.get("api_key") or ""
        v["api_key"] = (key[:4] + "…" + key[-4:]) if len(key) > 10 else ("•" * len(key) if key else "")
        v["has_key"] = bool(key)
        v.pop("api_key", None)
    return c


def _headers(p: dict) -> dict:
    h = {"Content-Type": "application/json"}
    if p.get("api_key"):
        h["Authorization"] = f"Bearer {p['api_key']}"
    return h


def test_provider(kind: str) -> dict:
    p = load_conns().get(kind)
    if not p or not p.get("base_url"):
        return {"ok": False, "error": "No base URL configured."}
    try:
        r = requests.get(p["base_url"].rstrip("/") + "/models",
                         headers=_headers(p), timeout=20)
        ok = r.status_code < 400
        return {"ok": ok, "status": r.status_code,
                "error": None if ok else r.text[:200]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


# ---------------- provider calls with failover ----------------

def llm_chat(kind: str, messages: list, temperature: float = 0.8,
             max_tokens: int = 2500, emit=None, json_mode: bool = False) -> tuple[str, str]:
    c = load_conns()
    p = c.get(kind)
    if not p or not p.get("base_url") or not p.get("models"):
        raise RuntimeError(f"No {kind} provider connected. Open Connections and add one.")
    last_err = None
    for model in p["models"]:
        body = {"model": model, "messages": messages,
                "temperature": temperature, "max_tokens": max_tokens}
        try:
            if json_mode:
                body["response_format"] = {"type": "json_object"}
            r = requests.post(p["base_url"].rstrip("/") + "/chat/completions",
                              headers=_headers(p), json=body, timeout=180)
            if r.status_code >= 400 and json_mode and "response_format" in body:
                body.pop("response_format")
                r = requests.post(p["base_url"].rstrip("/") + "/chat/completions",
                                  headers=_headers(p), json=body, timeout=180)
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
            return content, model
        except Exception as e:
            last_err = e
            if emit:
                emit({"type": "warning", "stage": kind,
                      "message": f"{model} failed ({str(e)[:120]}) — switching model with full context."})
    raise RuntimeError(f"All {kind} models failed. Last error: {last_err}")


def llm_visionDescribe(image_path: Path, prompt: str, emit=None) -> str:
    c = load_conns()
    p = c["text"]
    if not p.get("vision"):
        raise RuntimeError("Vision is not enabled on the text provider.")
    b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
    ext = Path(image_path).suffix.lower().lstrip(".") or "jpeg"
    mime = "image/png" if ext == "png" else "image/jpeg"
    messages = [{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
    ]}]
    content, _ = llm_chat("text", messages, temperature=0.4, max_tokens=600, emit=emit)
    return content


def audio_provider_speech(text: str, model: str | None = None,
                          voice: str | None = None) -> Path:
    """OpenAI-compatible /audio/speech. Returns a wav path (converted)."""
    c = load_conns()
    p = c["audio"]
    if not p.get("base_url"):
        raise RuntimeError("No audio provider connected.")
    model = model or (p["models"][0] if p["models"] else None)
    if not model:
        raise RuntimeError("Audio provider has no model id.")
    voice = voice or p.get("voice") or "alloy"
    r = requests.post(p["base_url"].rstrip("/") + "/audio/speech",
                      headers=_headers(p),
                      json={"model": model, "input": text, "voice": voice,
                            "response_format": "mp3"},
                      timeout=300)
    r.raise_for_status()
    import subprocess
    tmp = config.OUTPUT_DIR / f"prov_{new_id('a')}.mp3"
    tmp.write_bytes(r.content)
    out = tmp.with_suffix(".wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(tmp),
                    "-ar", "22050", "-ac", "1", str(out)], check=True,
                   capture_output=True)
    tmp.unlink(missing_ok=True)
    return out


def image_provider(prompt: str, size: str = "1280x720") -> Path:
    c = load_conns()
    p = c["visual"]
    if not p.get("base_url") or not p.get("models"):
        raise RuntimeError("No visual provider connected.")
    last = None
    for model in p["models"]:
        try:
            r = requests.post(p["base_url"].rstrip("/") + "/images/generations",
                              headers=_headers(p),
                              json={"model": model, "prompt": prompt,
                                    "n": 1, "size": size,
                                    "response_format": "b64_json"},
                              timeout=300)
            r.raise_for_status()
            data = r.json()["data"][0]
            if data.get("b64_json"):
                raw = base64.b64decode(data["b64_json"])
            elif data.get("url"):
                raw = requests.get(data["url"], timeout=120).content
            else:
                raise RuntimeError("No image payload in response.")
            out = config.OUTPUT_DIR / f"img_{new_id('i')}.png"
            out.write_bytes(raw)
            return out
        except Exception as e:
            last = e
    raise RuntimeError(f"Image provider failed: {last}")


# ---------------- job plumbing ----------------

class Job:
    def __init__(self, job_id: str):
        self.id = job_id
        self.q: queue.Queue = queue.Queue()
        self.state = "queued"
        self.stage = ""
        self.progress = 0.0
        self.confirm_event = threading.Event()
        self.confirm_payload = None
        self.result = None
        self.error = None
        self.created = time.time()
        self.cancelled = False

    def emit(self, ev: dict):
        ev = {"ts": round(time.time() - self.created, 1), **ev}
        self.q.put(ev)
        if ev.get("type") in ("stage_start",):
            self.stage = ev.get("stage", self.stage)
            self.state = "running"
        if ev.get("type") == "stage_progress":
            self.progress = float(ev.get("pct", self.progress))
        if ev.get("type") == "awaiting_confirmation":
            self.state = "awaiting_confirmation"
        if ev.get("type") == "done":
            self.state = "done"
            self.result = ev.get("result")
        if ev.get("type") == "error":
            self.state = "error"
            self.error = ev.get("message")

    def snapshot(self) -> dict:
        return {"id": self.id, "state": self.state, "stage": self.stage,
                "progress": round(self.progress, 3), "error": self.error,
                "result": self.result}


def get_job(jid: str) -> Job | None:
    with JOBS_LOCK:
        return JOBS.get(jid)


def _request_confirm(job: Job, stage: str, payload: dict) -> dict | None:
    """Pause for user approval. Returns edited payload or None if cancelled."""
    job.confirm_payload = None
    job.confirm_event.clear()
    job.emit({"type": "awaiting_confirmation", "stage": stage, "payload": payload})
    job.confirm_event.wait()
    if job.cancelled:
        raise RuntimeError("Cancelled by user.")
    return job.confirm_payload


# ---------------- pipeline ----------------

SYSTEM_SCRIPT = (
    "You are the head scriptwriter of a video studio. The user gives a topic "
    "and a target duration. Return STRICT JSON only, no prose:\n"
    '{"title": str, "scenes": [{"narration": str, "visual": {"type": "title|points|quote|wave|end", '
    '"text": str, "sub": str?, "points": [str]?}, "est_seconds": number}]}\n'
    "Rules: narration is what the voice SAYS (plain text, no scene directions, no emojis). "
    "visual.text is what appears ON SCREEN (short, punchy). First scene type=title, last "
    "scene type=end. Aim spoken words per scene ≈ est_seconds * 2.4. Keep each scene's "
    "narration between 8 and 45 words. Write everything in the SAME LANGUAGE as the user's prompt."
)


def _parse_json_loose(s: str) -> dict:
    s = re.sub(r"^```(?:json)?|```$", "", s.strip(), flags=re.M).strip()
    try:
        return json.loads(s)
    except Exception:
        m = re.search(r"\{.*\}", s, re.S)
        if m:
            return json.loads(m.group(0))
        raise


def run_pipeline(job: Job, spec: dict) -> None:
    """spec: {prompt, duration, voice_id, audio_source: local|provider,
               fit: natural|strict, aspect, confirm: bool, attachments: [paths]}"""
    try:
        out_dir = config.OUTPUT_DIR / f"agent_{job.id}"
        out_dir.mkdir(parents=True, exist_ok=True)

        # ---------- stage 1: script ----------
        job.emit({"type": "stage_start", "stage": "script",
                  "message": "Writing the script with your text model..."})
        user_msg = (f"Topic: {spec['prompt']}\n"
                    f"Target duration: about {spec.get('duration', 60)} seconds. "
                    f"That is roughly {int(spec.get('duration', 60) * 2.4)} spoken words in total.")
        content, used = llm_chat("text", [
            {"role": "system", "content": SYSTEM_SCRIPT},
            {"role": "user", "content": user_msg},
        ], temperature=0.85, emit=job.emit, json_mode=True)
        script = _parse_json_loose(content)
        scenes = script.get("scenes") or []
        if not scenes:
            raise RuntimeError("The model returned no scenes.")
        job.emit({"type": "stage_done", "stage": "script",
                  "message": f"Script ready ({len(scenes)} scenes) via {used}.",
                  "data": {"title": script.get("title"), "scenes": scenes}})

        if spec.get("confirm", True):
            edited = _request_confirm(job, "script",
                                      {"title": script.get("title", ""), "scenes": scenes})
            if edited:
                script["title"] = edited.get("title", script.get("title"))
                scenes = edited.get("scenes", scenes)

        # ---------- stage 2: plan ----------
        job.emit({"type": "stage_start", "stage": "plan",
                  "message": "Fitting scene timings to the target duration..."})
        total_words = sum(len((s.get("narration") or "").split()) for s in scenes) or 1
        target = float(spec.get("duration") or 60)
        scale = target / max(total_words / 2.4, 1.0)
        planned = []
        for s in scenes:
            words = len((s.get("narration") or "").split())
            dur = max(2.5, (words / 2.4) * scale + 0.6)
            v = s.get("visual") or {}
            planned.append({
                "narration": s.get("narration", ""),
                "type": v.get("type", "points" if v.get("points") else "title"),
                "text": v.get("text") or s.get("narration", "")[:80],
                "sub": v.get("sub"),
                "points": v.get("points"),
                "duration": round(dur, 2),
            })
        planned_total = sum(p["duration"] for p in planned)
        job.emit({"type": "stage_done", "stage": "plan",
                  "message": f"Plan: {len(planned)} scenes, ~{planned_total:.0f}s "
                             f"(target {target:.0f}s, drift {planned_total - target:+.0f}s).",
                  "data": {"scenes": planned}})

        # ---------- stage 3: attachments (vision) ----------
        attachments = spec.get("attachments") or []
        if attachments:
            job.emit({"type": "stage_start", "stage": "vision",
                      "message": f"Understanding {len(attachments)} attachment(s)..."})
            texts = load_conns()["text"]
            if not texts.get("vision"):
                job.emit({"type": "warning", "stage": "vision",
                          "message": "Attachments need a vision-capable text model — "
                                     "enable 'vision' in Connections or remove them. Skipping."})
            else:
                for i, att in enumerate(attachments):
                    ap = Path(att)
                    if not ap.exists():
                        continue
                    if ap.suffix.lower() in (".mp4", ".mov", ".webm", ".mkv"):
                        frame = out_dir / f"att{i}_frame.jpg"
                        import subprocess as sp
                        sp.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "1",
                                "-i", str(ap), "-frames:v", "1", str(frame)],
                               check=True, capture_output=True)
                        ap = frame
                    if ap.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
                        continue
                    try:
                        desc = llm_visionDescribe(
                            ap, "Describe this image in 2 short sentences: what it shows and the mood. "
                                "Be concrete.", emit=job.emit)
                        job.emit({"type": "stage_progress", "stage": "vision",
                                  "pct": (i + 1) / len(attachments),
                                  "message": f"Attachment {i + 1}: {desc[:80]}..."})
                        planned[min(i, len(planned) - 1)]["_image_path"] = str(ap)
                        planned[min(i, len(planned) - 1)]["sub"] = \
                            (planned[min(i, len(planned) - 1)].get("sub") or "") + (f" {desc[:90]}" if i == 0 else "")
                    except Exception as e:
                        job.emit({"type": "warning", "stage": "vision",
                                  "message": f"Vision failed on attachment {i + 1}: {str(e)[:120]}"})
                job.emit({"type": "stage_done", "stage": "vision",
                          "message": "Attachment review finished."})

        # ---------- stage 4: audio ----------
        job.emit({"type": "stage_start", "stage": "audio",
                  "message": "Voicing every scene..."})
        from storage import get_voice
        voice = get_voice(spec.get("voice_id") or "") if spec.get("voice_id") else None
        use_provider = spec.get("audio_source") == "provider"
        audios: list[Path] = []
        for i, sc in enumerate(planned):
            job.emit({"type": "stage_progress", "stage": "audio",
                      "pct": i / len(planned),
                      "message": f"Scene {i + 1}/{len(planned)}: “{(sc['narration'] or '')[:48]}…”"})
            wav = out_dir / f"scene{i:02d}.wav"
            ok = False
            if use_provider:
                try:
                    wav = audio_provider_speech(sc["narration"])
                    ok = True
                    job.emit({"type": "info", "stage": "audio",
                              "message": f"Scene {i + 1} voiced by the connected audio model."})
                except Exception as e:
                    job.emit({"type": "warning", "stage": "audio",
                              "message": f"Audio provider failed ({str(e)[:100]}) — falling back to the local cloned voice."})
            if not ok:
                if not voice:
                    raise RuntimeError("Pick a voice in the Library first (or connect an audio provider).")
                engine.generate(sc["narration"], voice["se_path"], wav,
                                speed=1.0, tau=0.3)
            import soundfile as sf
            dur = sf.info(str(wav)).duration
            slot = sc["duration"]
            if spec.get("fit", "natural") == "strict" and dur > slot:
                sc["_fit"] = min(1.25, dur / slot)
            else:
                sc["duration"] = round(dur + 0.45, 2)   # visual breathes with the audio
            audios.append(wav)
        new_total = sum(sc["duration"] for sc in planned)
        job.emit({"type": "stage_done", "stage": "audio",
                  "message": f"Audio ready — final length ≈ {new_total:.0f}s.",
                  "data": {"scenes": [{k: v for k, v in sc.items() if not k.startswith('_')} for sc in planned]}})

        if spec.get("confirm", True):
            edited = _request_confirm(job, "audio", {"scenes": planned})
            if edited:
                planned = edited.get("scenes", planned)

        # ---------- stage 5: visuals ----------
        job.emit({"type": "stage_start", "stage": "visuals",
                  "message": "Rendering scenes (motion engine)..."})
        clips = []
        vis = load_conns()["visual"]
        for i, sc in enumerate(planned):
            scene = {k: v for k, v in sc.items() if not k.startswith("_")}
            # try connected image provider for image scenes
            if scene.get("type") == "image" or vis.get("base_url"):
                pass  # image scenes only rendered from attachments/generated art in v1
            clip = out_dir / f"scene{i:02d}.mp4"
            motion.render_scene(scene, audios[i], clip, out_dir / f"render{i:02d}",
                                progress=(lambda p, i=i: job.emit(
                                    {"type": "stage_progress", "stage": "visuals",
                                     "pct": (i + p) / len(planned),
                                     "message": f"Scene {i + 1}/{len(planned)} frames {int(p * 100)}%"})))
            clips.append(clip)
            job.emit({"type": "info", "stage": "visuals",
                      "message": f"Scene {i + 1} rendered."})
        job.emit({"type": "stage_done", "stage": "visuals",
                  "message": f"{len(clips)} scenes rendered."})

        # ---------- stage 6: final render ----------
        job.emit({"type": "stage_start", "stage": "render",
                  "message": "Stitching + muxing audio..."})
        full_audio = out_dir / "narration_full.wav"
        import soundfile as sf
        import numpy as np
        pieces = []
        for w in audios:
            x, sr = sf.read(str(w), dtype="float32", always_2d=True)
            pieces.append(x.mean(axis=1))
            pieces.append(np.zeros(int(0.45 * sr), dtype=np.float32))
        sf.write(str(full_audio), np.concatenate(pieces).astype(np.float32), 22050)
        title = re.sub(r"[^\w-]+", "_", (script.get("title") or "InsaneVoice_Video"))[:60]
        final = config.OUTPUT_DIR / f"{title}.mp4"
        motion.concat_scenes(clips, full_audio, final)
        job.emit({"type": "done", "stage": "render",
                  "message": f"Video ready: {final.name}",
                  "result": {"video_url": f"/api/agent/video/{final.name}",
                             "file": final.name, "title": script.get("title"),
                             "scenes": len(planned), "duration": round(new_total, 1)}})
    except Exception as e:
        job.emit({"type": "error", "message": str(e)[:600]})
        import traceback
        print("[agent] FAILED:", e, "\n", traceback.format_exc()[-1500:], flush=True)


def start_job(spec: dict) -> dict:
    jid = new_id("job")
    job = Job(jid)
    with JOBS_LOCK:
        # keep only the last 4 jobs around
        while len(JOBS) > 4:
            old = sorted(JOBS.values(), key=lambda j: j.created)[0]
            if old.state in ("done", "error"):
                del JOBS[old.id]
            else:
                break
        JOBS[jid] = job
    threading.Thread(target=run_pipeline, args=(job, spec), daemon=True).start()
    return job.snapshot()


def confirm_job(jid: str, payload=None, cancel: bool = False) -> dict:
    job = get_job(jid)
    if not job:
        raise RuntimeError("Unknown job.")
    job.confirm_payload = payload
    job.cancelled = cancel
    job.confirm_event.set()
    if cancel:
        job.emit({"type": "error", "message": "Cancelled by user."})
    return job.snapshot()
