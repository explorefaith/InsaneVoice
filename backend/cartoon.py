"""Cartoon Studio — one free 2D cartoon per user per day.

Pipeline (all cloud, ffmpeg render):
    text model  (TokenHarbor, mimo → deepseek failover)  → 9-scene script
    image model (OpenRouter, Recraft)                    → 9 scene images
    vision model(TokenHarbor, mimo)                      → QC pass, 1 regen each
    audio model (OpenRouter, Fish Audio)                 → narration mp3
    local numpy lullaby + ffmpeg                         → ~60s 1080p mp4

Providers live in <data>/cartoon_providers.json (never committed).
Quota: <data>/cartoon_quota.json  — 1 finished job per client per local day.
Jobs:  <data>/cartoon/jobs.json   — last 8 kept, dirs job_<id>/.
"""
from __future__ import annotations

import base64
import json
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
import wave
from datetime import date
from pathlib import Path

import config

PROVIDERS_FILE = config.DATA_DIR / "cartoon_providers.json"
QUOTA_FILE = config.DATA_DIR / "cartoon_quota.json"
JOBS_DIR = config.DATA_DIR / "cartoon"
JOBS_FILE = JOBS_DIR / "jobs.json"
DAILY_LIMIT = 1          # per client per local day
KEEP_JOBS = 8

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
STYLE_BASE = ("Flat 2D vector cartoon, storybook illustration, clean shapes, soft "
              "warm lighting, cohesive palette. Wide 16:9 cinematic composition. "
              "No text, no speech bubbles, no watermark.")

TRANSITIONS = ("fade", "smoothleft", "circleopen", "wipeleft", "dissolve",
               "slideright", "radial", "smoothup")

# caption fonts per script system (drawtext needs a font that covers the script)
LANG_FONT = {
    "hi": "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
    "bn": "/usr/share/fonts/truetype/noto/NotoSansBengali-Bold.ttf",
}
LANG_DIRECTIVE = {
    "hi": "Write ALL narration and captions in HINDI (Devanagari script) — natural, "
          "simple, warm storytelling Hindi that a text-to-speech voice reads smoothly.",
}

def _caption_font(lang: str) -> str:
    return LANG_FONT.get((lang or "en").lower(), FONT)

_lock = threading.Lock()          # one job at a time
_jobs: dict = {}                  # job_id -> job dict (mirror of jobs.json)


# ---------- providers ----------

def _providers() -> dict:
    if not PROVIDERS_FILE.exists():
        raise RuntimeError(
            "Cartoon providers not configured — create "
            f"{PROVIDERS_FILE} with text/vision/image/tts endpoints.")
    return json.loads(PROVIDERS_FILE.read_text())


# ---------- quota ----------

def _today() -> str:
    return date.today().isoformat()


def _quota_map() -> dict:
    try:
        return json.loads(QUOTA_FILE.read_text())
    except Exception:
        return {}


def quota_for(client_id: str) -> dict:
    q = _quota_map().get(client_id, {})
    used = q.get("count", 0) if q.get("date") == _today() else 0
    return {"used": used, "limit": DAILY_LIMIT, "remaining": max(0, DAILY_LIMIT - used),
            "date": _today()}


def _mark_used(client_id: str) -> None:
    q = _quota_map()
    cur = q.get(client_id, {})
    if cur.get("date") != _today():
        cur = {"date": _today(), "count": 0}
    cur["count"] += 1
    q[client_id] = cur
    QUOTA_FILE.write_text(json.dumps(q, indent=1))


# ---------- jobs ----------

def _save_jobs() -> None:
    JOBS_FILE.write_text(json.dumps(_jobs, indent=1))


def _load_jobs() -> None:
    global _jobs
    try:
        _jobs = json.loads(JOBS_FILE.read_text())
    except Exception:
        _jobs = {}
    # worker threads don't survive a restart — fail interrupted jobs cleanly
    for j in _jobs.values():
        if j.get("status") == "running":
            j["status"] = "error"
            j["message"] = "Interrupted by engine restart — try again (no quota used)."
            j["error"] = j["message"]
            j["finished"] = time.time()


def _update(job_id: str, **fields) -> None:
    job = _jobs.get(job_id)
    if not job:
        return
    job.update(fields)
    _save_jobs()


def active_job_for(client_id: str) -> dict | None:
    for j in _jobs.values():
        if j.get("client") == client_id and j.get("status") == "running":
            return j
    return None


def get_job(job_id: str) -> dict | None:
    return _jobs.get(job_id)


def job_video(job_id: str) -> Path | None:
    p = JOBS_DIR / f"job_{job_id}" / "cartoon.mp4"
    return p if p.exists() else None


def library(limit: int = 6) -> list[dict]:
    done = [j for j in _jobs.values() if j.get("status") == "done"]
    done.sort(key=lambda j: j.get("finished", 0), reverse=True)
    return [{"id": j["id"], "title": j.get("title", "Cartoon"),
             "duration": j.get("duration"), "finished": j.get("finished")}
            for j in done[:limit]]


def start_job(client_id: str, idea: str, mode: str = "motion", lang: str = "en") -> dict:
    with _lock:
        if active_job_for(client_id):
            raise RuntimeError("Your previous cartoon is still generating — one at a time.")
        q = quota_for(client_id)
        if q["remaining"] <= 0:
            raise PermissionError(
                "Daily free cartoon used. Come back tomorrow — resets at midnight.")
        jid = uuid.uuid4().hex[:12]
        job = {"id": jid, "client": client_id, "status": "running",
               "stage": "script", "progress": 0.02,
               "message": "Writing the script…", "idea": (idea or "").strip(),
               "mode": "storybook" if mode == "storybook" else "motion",
               "lang": (lang or "en").lower()[:8],
               "started": time.time(), "error": None}
        _jobs[jid] = job
        _prune_old_jobs()
        _save_jobs()
        threading.Thread(target=_worker, args=(job,), daemon=True).start()
        return dict(job)


def _prune_old_jobs() -> None:
    done = sorted((j for j in _jobs.values() if j.get("status") == "done"),
                  key=lambda j: j.get("finished", 0))
    for j in done[:-KEEP_JOBS]:
        _jobs.pop(j["id"], None)
        d = JOBS_DIR / f"job_{j['id']}"
        if d.exists():
            subprocess.run(["rm", "-rf", str(d)], check=False)


# ---------- http helper ----------

def _post_json(url: str, key: str, payload: dict, timeout: int = 240) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _retry(fn, tries: int = 3, wait: int = 5, rate_limit_wait: int = 60):
    """Retry flaky free-tier calls. HTTP 429 gets a long cooldown instead of
    counting as a fast failure — rate-limit windows outlast short backoffs."""
    last = None
    for i in range(tries):
        try:
            return fn()
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429 and i < tries - 1:
                print(f"[cartoon] rate limited, cooling down {rate_limit_wait}s "
                      f"(attempt {i+1}/{tries})", flush=True)
                time.sleep(rate_limit_wait)
                continue
            time.sleep(wait)
        except Exception as e:      # noqa: BLE001 — free endpoints are flaky
            last = e
            time.sleep(wait * (i + 1))
    raise RuntimeError(f"all {tries} attempts failed: {last}")


def _probe(path: Path) -> float:
    o = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return float(o.stdout.strip())


# ---------- worker ----------

def _worker(job: dict) -> None:
    jid = job["id"]
    d = JOBS_DIR / f"job_{jid}"
    d.mkdir(parents=True, exist_ok=True)
    try:
        p = _providers()
        script = _stage_script(job, p, d)          # includes premise stage
        durs = _stage_tts(job, p, d, script)
        if job.get("mode") == "motion":
            _stage_motion(job, p, d, script, durs)
        else:
            _stage_images(job, p, d, script)
        _stage_music(d)
        _stage_render(job, d, script, durs)
        video = d / "cartoon.mp4"
        _update(jid, status="done", stage="done", progress=1.0,
                message="Your cartoon is ready!", duration=round(_probe(video), 1),
                title=script.get("title", "Cartoon"), finished=time.time())
        _mark_used(job["client"])
    except Exception as e:      # noqa: BLE001 — report any failure to the client
        msg = str(e)
        if "429" in msg:
            msg = ("A cloud model hit its free daily limit (resets at midnight UTC). "
                   "Your quota was not used — try again tomorrow.")
        _update(jid, status="error", message=msg[:400],
                error=msg[:400], finished=time.time())


# ---------- stage 0: premise (fresh story + character every run) ----------

def _stage_premise(job: dict, p: dict, d: Path) -> dict:
    f = d / "premise.json"
    if f.exists():
        return json.loads(f.read_text())
    idea = (job.get("idea") or "").strip()
    used = [j.get("title") for j in _jobs.values() if j.get("title")]
    avoid = ("Avoid these already-used premises: " + "; ".join(used[:10]) + ". ") if used else ""
    if idea:
        task = f'Build the cartoon premise around this user idea: "{idea}".'
    else:
        task = ("Invent a COMPLETELY RANDOM, fresh premise: pick a surprising main "
                "character (an animal, object, or little creature — not a robot), an "
                "unexpected setting (space, jungle, kitchen, ocean floor, rooftop, "
                "library, mountain, toy shop...), a tiny problem, and a warm or funny "
                "resolution with a small twist. Vary the genre boldly. " + avoid)
    prompt = f"""{task}

Return STRICT JSON only, no markdown fences:
{{"title": "...", "character": "one-sentence physical description of the main character for an artist — shape, colors, one distinguishing feature", "logline": "one sentence: what happens", "mood": "one of: cozy, playful, dreamy, adventurous, funny"}}"""
    last_err = None
    for model in p["text"]["models"]:
        try:
            r = _post_json(f"{p['text']['base_url']}/chat/completions",
                           p["text"]["api_key"], {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 1.0, "max_tokens": 500}, timeout=120)
            txt = r["choices"][0]["message"]["content"].strip()
            txt = txt.split("```json")[-1].split("```")[0].strip()
            data = json.loads(txt[txt.index("{"): txt.rindex("}") + 1])
            assert data.get("title") and data.get("character") and data.get("logline")
            data.setdefault("mood", "cozy")
            f.write_text(json.dumps(data, indent=1))
            print(f"[cartoon] premise: {data['title']} — {data['logline']}", flush=True)
            return data
        except urllib.error.HTTPError as e:
            last_err = f"{model}: HTTP {e.code}"; time.sleep(4)
        except Exception as e:      # noqa: BLE001
            last_err = f"{model}: {e}"; time.sleep(4)
    raise RuntimeError(f"premise generation failed: {last_err}")


# ---------- stage 1: script ----------

def _stage_script(job: dict, p: dict, d: Path) -> dict:
    _update(job["id"], stage="script", progress=0.05, message="Writing the script…")
    premise = _stage_premise(job, p, d)
    idea_block = (f'Title: "{premise["title"]}". '
                  f'Main character: {premise["character"]} '
                  f'(this EXACT character must appear in every scene, same colors/shape). '
                  f'Story: {premise["logline"]} Expand it into 8 beats + closing card. '
                  f'Mood: {premise.get("mood", "cozy")}.')
    prompt = f"""Write a script for a 60-second heartwarming 2D cartoon for a faceless YouTube channel.

{LANG_DIRECTIVE.get((job.get("lang") or "en").lower(), "")}
{idea_block}

Return STRICT JSON only, no markdown fences, exactly this shape:
{{"title": "...", "scenes": [
  {{"narration": "...", "visual": "...", "caption": "..."}}
]}}

Rules:
- Exactly 9 items. Items 1-8 are story scenes; item 9 is the closing card (narration one short warm goodnight/goodbye line, visual: cozy "the end" style card of the main character resting/safe, caption empty string "").
- Total narration 135-150 words (~60 seconds at a calm storytelling pace), split across scenes (roughly 15-20 words each, closing card 3-6 words).
- "visual": a detailed scene description. Mention the main character's ACTION + what else is in frame + mood. Every scene must feature the main character. Do NOT include art-style words (style is added separately).
- "caption": max 5 words, shown as on-screen text. For the last card use ""."""
    payload = {"messages": [{"role": "user", "content": prompt}],
               "temperature": 0.8, "max_tokens": 2000}
    txt_cfg = p["text"]
    attempts = [m for m in txt_cfg["models"] for _ in range(2)]   # 2 tries each
    last_err = None
    for model in attempts:
        try:
            r = _post_json(f"{txt_cfg['base_url']}/chat/completions",
                           txt_cfg["api_key"], {**payload, "model": model},
                           timeout=240)
            txt = r["choices"][0]["message"]["content"].strip()
            txt = txt.split("```json")[-1].split("```")[0].strip()
            data = json.loads(txt[txt.index("{"): txt.rindex("}") + 1])
            if len(data.get("scenes", [])) != 9:
                raise ValueError(f"want 9 scenes, got {len(data.get('scenes', []))}")
            (d / "script.json").write_text(json.dumps(data, indent=1))
            return data
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode()[:200]
            except Exception:
                pass
            last_err = f"{model}: HTTP {e.code} {body}"
            print(f"[cartoon] script attempt failed: {last_err}", flush=True)
            time.sleep(5)
        except Exception as e:      # noqa: BLE001
            last_err = f"{model}: {type(e).__name__}: {e}"
            print(f"[cartoon] script attempt failed: {last_err}", flush=True)
            time.sleep(5)
    raise RuntimeError(f"script generation failed on all text models (last: {last_err})")


# ---------- stage 2: images + vision QC ----------

def _gen_image(p: dict, prompt: str, out_png: Path) -> None:
    r = _retry(lambda: _post_json(f"{p['image']['base_url']}/chat/completions",
                                  p["image"]["api_key"], {
        "model": p["image"]["model"], "modalities": ["image"],
        "messages": [{"role": "user", "content": prompt}]}, timeout=240),
        tries=5, wait=8, rate_limit_wait=75)
    url = r["choices"][0]["message"]["images"][0]["image_url"]["url"]
    raw = out_png.with_suffix(".webp")
    raw.write_bytes(base64.b64decode(url.split("base64,", 1)[1]))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(raw),
                    "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,"
                           "crop=1920:1080", str(out_png)], check=True)
    raw.unlink()


def _qc_images(p: dict, pngs: list[Path]) -> set[int]:
    """One vision call over all frames; returns indices that must be regenerated."""
    content = [{"type": "text", "text":
        "These are 2D cartoon scene images in order. Each must show a small round "
        "orange robot with an antenna ball. Reply STRICT JSON: "
        '{"bad": [indices of broken images], "why": "..."} — bad means garbled '
        "image, wrong/missing character, or heavy artifacts. 0-based."}]
    for png in pngs:
        b64 = base64.b64encode(png.read_bytes()).decode()
        content.append({"type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    v = p["vision"]
    try:
        r = _post_json(f"{v['base_url']}/chat/completions", v["api_key"], {
            "model": v["model"], "max_tokens": 300,
            "messages": [{"role": "user", "content": content}]}, timeout=180)
        txt = r["choices"][0]["message"]["content"].strip()
        txt = txt.split("```json")[-1].split("```")[0].strip()
        bad = json.loads(txt[txt.index("{"): txt.rindex("}") + 1]).get("bad", [])
        return {int(i) for i in bad if isinstance(i, (int, str)) and str(i).isdigit()}
    except Exception:
        return set()            # QC is best-effort, never fatal


def _stage_images(job: dict, p: dict, d: Path, script: dict) -> None:
    n = len(script["scenes"])
    try:
        character = json.loads((d / "premise.json").read_text())["character"]
    except Exception:                       # noqa: BLE001
        character = "a small round orange robot with big teal eyes"
    pngs = []
    for i, sc in enumerate(script["scenes"], 1):
        _update(job["id"], stage="images", progress=0.05 + 0.42 * i / n,
                message=f"Painting scene {i} of {n}…")
        png = d / f"scene{i}.png"
        if not png.exists():
            _gen_image(p, f"{sc['visual']}. Character: {character}. {STYLE_BASE}", png)
        pngs.append(png)
        time.sleep(1.5)
    _update(job["id"], progress=0.5, message="Checking scenes with vision…")
    bad = _qc_images(p, pngs)
    for i in sorted(bad):
        if 1 <= i + 1 <= n:
            png = d / f"scene{i+1}.png"
            png.unlink(missing_ok=True)
            _gen_image(p, f"{script['scenes'][i]['visual']}. Character: {character}. {STYLE_BASE}", png)
            time.sleep(1.5)


# ---------- stage 3: narration ----------

def _stage_tts(job: dict, p: dict, d: Path, script: dict) -> dict:
    durs = {}
    n = sum(1 for sc in script["scenes"] if sc.get("narration"))
    done = 0
    lang = (job.get("lang") or "en").lower()
    cloud_dead = False          # once the daily cap is hit, stop wasting retries
    for i, sc in enumerate(script["scenes"], 1):
        if not sc.get("narration"):
            continue
        _update(job["id"], stage="narration", progress=0.52 + 0.13 * done / n,
                message=f"Recording narration {done+1} of {n}…")
        mp3 = d / f"narr{i}.mp3"
        if not mp3.exists():
            used_cloud = False
            if not cloud_dead:
                try:
                    req = urllib.request.Request(f"{p['tts']['base_url']}/audio/speech",
                        data=json.dumps({"model": p["tts"]["model"],
                                         "input": sc["narration"],
                                         "response_format": "mp3"}).encode(),
                        headers={"Authorization": f"Bearer {p['tts']['api_key']}",
                                 "Content-Type": "application/json"})
                    def _tts():
                        with urllib.request.urlopen(req, timeout=120) as r:
                            mp3.write_bytes(r.read())
                    _retry(_tts, tries=3, wait=4)
                    used_cloud = True
                except Exception as e:      # noqa: BLE001 — offline fallback
                    if "429" not in str(e):
                        raise
                    cloud_dead = True       # daily cap — straight to MMS from now on
                    print(f"[cartoon] tts {i}: cloud daily cap hit — local MMS for the "
                          f"rest of this job", flush=True)
            if not used_cloud:
                print(f"[cartoon] tts {i}: local MMS narration", flush=True)
                _mms_tts(sc["narration"], lang, mp3)
        durs[f"n{i}"] = _probe(mp3)
        done += 1
        time.sleep(1)
    return durs


def _mms_tts(text: str, lang: str, out_path: Path) -> None:
    """Offline narration with the engine's Meta MMS base TTS (no cloud quota)."""
    import engine, langs
    iso = langs.MMS_ISO.get(lang)
    if not iso:
        raise RuntimeError(f"cloud TTS rate-limited and no offline voice for '{lang}'")
    engine.mms_generate(text, iso, str(out_path) + ".wav", speed=1.10)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(out_path) + ".wav",
                    "-b:a", "128k", str(out_path)], check=True)
    Path(str(out_path) + ".wav").unlink(missing_ok=True)


# ---------- stage 3b: HTML motion scenes (with image fallback) ----------

def scene_len(nd: float) -> float:
    """Scene duration from narration length — shared by capture and render."""
    return max(round(nd / 1.10 + 1.0, 2), 5.5)   # 0.4s lead + 0.6s tail, 1.10x


def _stage_motion(job: dict, p: dict, d: Path, script: dict, durs: dict) -> None:
    import cartoon_motion as cmotion
    from concurrent.futures import ThreadPoolExecutor, as_completed
    n = len(script["scenes"])
    try:
        premise = json.loads((d / "premise.json").read_text())
        character, mood = premise["character"], premise.get("mood", "cozy")
    except Exception:                       # noqa: BLE001 — premise optional
        character, mood = "a small round orange robot with big teal eyes", "cozy"
    # deepseek writes HTML ~5x faster than mimo — flip the order for this stage
    cfg_motion = {**p["text"], "models": list(reversed(p["text"]["models"]))}

    # phase A — parallel LLM calls (network-bound, no browser)
    raw: dict[int, str] = {}
    errors: dict[int, str] = {}
    lens = {i: scene_len(durs.get(f"n{i}", 0.0)) for i in range(1, n + 1)}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futs = {pool.submit(cmotion.request_scene_html, cfg_motion, sc, lens[i],
                            character,
                            (0.4, 0.4 + durs.get(f"n{i}", 0.0) / 1.10)
                            if durs.get(f"n{i}") else None,
                            mood): i
                for i, sc in enumerate(script["scenes"], 1)}
        done = 0
        for fut in as_completed(futs):
            i = futs[fut]
            done += 1
            _update(job["id"], stage="animation", progress=0.30 + 0.12 * done / n,
                    message=f"Writing animation {done} of {n}…")
            try:
                raw[i] = fut.result()
            except Exception as e:          # noqa: BLE001
                errors[i] = str(e)

    # phase B — serial: write, validate in Chrome, capture frames
    with cmotion.MotionRenderer() as mr:
        for i, sc in enumerate(script["scenes"], 1):
            _update(job["id"], stage="animation", progress=0.42 + 0.13 * i / n,
                    message=f"Filming scene {i} of {n}…")
            frames_dir = d / f"frames{i}"
            if frames_dir.exists() and any(frames_dir.iterdir()):
                continue
            html_path = d / f"scene{i}.html"
            ok = False
            # candidate 1: the parallel result from phase A
            if i in raw:
                try:
                    html_path.write_text(raw[i])
                    mr.validate(html_path, lens[i])
                    mr.capture(html_path, lens[i], frames_dir)
                    ok = True
                except Exception as e:      # noqa: BLE001
                    print(f"[cartoon] scene {i}: parallel candidate rejected ({e})",
                          flush=True)
            # candidate 2: one serial retry (mimo first) — only if needed
            if not ok:
                try:
                    html = cmotion.request_scene_html(
                        p["text"], sc, lens[i], character,
                        (0.4, 0.4 + durs.get(f"n{i}", 0.0) / 1.10)
                        if durs.get(f"n{i}") else None, mood)
                    html_path.write_text(html)
                    mr.validate(html_path, lens[i])
                    mr.capture(html_path, lens[i], frames_dir)
                    ok = True
                except Exception as e:      # noqa: BLE001
                    errors[i] = str(e)
                    print(f"[cartoon] scene {i}: html request failed: {e}", flush=True)
            if ok:
                errors.pop(i, None)
                print(f"[cartoon] scene {i}: motion frames OK", flush=True)
            else:
                print(f"[cartoon] scene {i}: motion failed — image fallback", flush=True)
                png = d / f"scene{i}.png"
                if not png.exists():
                    _gen_image(p, f"{sc['visual']}. Character: {character}. {STYLE_BASE}", png)
                time.sleep(1.5)
    _update(job["id"], stage="animation", progress=0.55, message="Scenes animated.")


# ---------- stage 4: lullaby ----------

def _place(sig, t, n, sr):
    import numpy as np
    i0 = int(t * sr); i1 = min(n, i0 + len(sig))
    if i0 >= n:
        return np.zeros(n)
    out = np.zeros(n)
    out[i0:i1] = sig[: i1 - i0]
    return out


def _stage_music(d: Path) -> None:
    wav = d / "music.wav"
    if wav.exists():
        return
    import numpy as np
    SR = 44100
    total = 64.0
    n = int(SR * total)
    audio = np.zeros(n)

    def pluck(freq, dur, vol):
        N = int(SR * dur)
        buf_n = int(SR / freq)
        buf = (np.random.rand(buf_n) * 2 - 1)
        out = np.zeros(N)
        for j in range(N):
            k = j % buf_n
            out[j] = buf[k]
            buf[k] = 0.996 * 0.5 * (buf[k] + buf[(k + 1) % buf_n])
        return out * np.exp(-np.linspace(0, 4.5, N)) * vol

    C5, D5, E5, G5, A5, C6 = 523.25, 587.33, 659.25, 783.99, 880.00, 1046.50
    melody = [C5, E5, G5, A5, G5, E5, D5, C5, E5, G5, C6, A5, G5, E5, D5, C5,
              C5, E5, G5, A5, C6, A5, G5, E5, G5, E5, D5, C5, D5, E5, G5, C5]
    t, mi = 0.0, 0
    while t < total - 2:
        if mi % 8 != 7:
            audio += _place(pluck(melody[mi % len(melody)], 1.6, 0.5), t, n, SR)
        if mi % 4 == 0:
            audio += _place(pluck(261.63, 2.0, 0.35), t, n, SR)
        t += 1.05; mi += 1
    audio /= max(1e-9, np.abs(audio).max())
    audio *= 0.35
    fi, fo = int(SR * 2), int(SR * 4)
    audio[:fi] *= np.linspace(0, 1, fi)
    audio[-fo:] *= np.linspace(1, 0, fo)
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((audio * 32767).astype(np.int16).tobytes())


# ---------- stage 5: render ----------

def _stage_render(job: dict, d: Path, script: dict, durs: dict) -> None:
    import cartoon_motion as cmotion
    fps = cmotion.FPS
    cap_font = _caption_font(job.get("lang", "en"))
    n = len(script["scenes"])
    clips = []
    for i, sc in enumerate(script["scenes"], 1):
        _update(job["id"], stage="render", progress=0.68 + 0.24 * i / n,
                message=f"Rendering clip {i} of {n}…")
        nd = durs.get(f"n{i}", 0.0)
        di = scene_len(nd)
        cp = d / f"clip{i}.mp4"
        clips.append((cp, di))
        if cp.exists():
            continue
        cap = d / f"cap{i}.txt"
        cap.write_text(sc.get("caption", ""))
        frames_dir = d / f"frames{i}"
        frames_seq = frames_dir.exists() and any(frames_dir.iterdir())
        frames = max(int(di * fps), 2)
        if frames_seq:
            vf = "scale=1920:1080,format=yuv420p"
            vcmd = ["-framerate", str(fps), "-i", str(frames_dir / "f%05d.png")]
        else:
            vf = (f"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,"
                  f"zoompan=z='min(1+0.0009*on,1.10)':x='iw/2-(iw/zoom/2)':"
                  f"y='ih/2-(ih/zoom/2)':d={frames}:s=1920x1080:fps={fps}")
            vcmd = ["-i", str(d / f"scene{i}.png")]
        if sc.get("caption"):
            vf += (f",drawtext=fontfile={cap_font}:textfile={cap}:fontsize=46:"
                   f"fontcolor=white:borderw=4:bordercolor=black@0.65:"
                   f"x=(w-text_w)/2:y=h-150")
        subprocess.run(["ffmpeg", "-y", "-v", "error"] + vcmd +
                       ["-i", str(d / f"narr{i}.mp3"),
                        "-filter_complex", vf,
                        "-af", "atempo=1.10,adelay=400:all=1,apad",
                        "-t", str(di), "-r", str(fps),
                        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
                        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                        str(cp)], check=True)
    final = d / "cartoon.mp4"
    durs_c = [dd for _, dd in clips]
    xf = 0.5
    inputs = []
    for cp, _ in clips:
        inputs += ["-i", str(cp)]
    fc = []
    prev_v, prev_a = "[0:v]", "[0:a]"
    offset = 0.0
    for k in range(1, n):
        offset += durs_c[k - 1] - xf
        trans = TRANSITIONS[(k - 1) % len(TRANSITIONS)]
        fc.append(f"{prev_v}[{k}:v]xfade=transition={trans}:duration={xf}:offset={offset:.3f}[v{k}]")
        fc.append(f"{prev_a}[{k}:a]acrossfade=d={xf}:c1=tri:c2=tri[a{k}]")
        prev_v, prev_a = f"[v{k}]", f"[a{k}]"
    fc.append(f"[{n}:a]volume=0.16[mus]")
    fc.append(f"{prev_a}[mus]amix=inputs=2:duration=first:normalize=0[mix]")
    _update(job["id"], progress=0.95, message="Final cut + music…")
    subprocess.run(["ffmpeg", "-y", "-v", "error"] + inputs +
                   ["-i", str(d / "music.wav"),
                    "-filter_complex", ";".join(fc), "-map", prev_v, "-map", "[mix]",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                    str(final)], check=True)


_load_jobs()
JOBS_DIR.mkdir(parents=True, exist_ok=True)
