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


def start_job(client_id: str, idea: str, mode: str = "motion", lang: str = "en",
              cast: str = "") -> dict:
    with _lock:
        mine = active_job_for(client_id)
        if mine:
            raise RuntimeError("Your previous cartoon is still generating — one at a time.")
        q = quota_for(client_id)
        if q["remaining"] <= 0:
            raise PermissionError(
                "Daily free cartoon used. Come back tomorrow — resets at midnight.")
        jid = uuid.uuid4().hex[:12]
        busy = any(j.get("status") == "running" for j in _jobs.values())
        job = {"id": jid, "client": client_id,
               "status": "queued" if busy else "running",
               "stage": "queue" if busy else "script", "progress": 0.0,
               "message": "Waiting for the current cartoon to finish…" if busy else "Writing the script…",
               "idea": (idea or "").strip(),
               "mode": "storybook" if mode == "storybook" else "motion",
               "lang": (lang or "en").lower()[:8],
               "cast": (cast or "").strip(),
               "started": time.time(), "error": None}
        _jobs[jid] = job
        _prune_old_jobs()
        _save_jobs()
        if job["status"] == "running":
            threading.Thread(target=_worker, args=(job,), daemon=True).start()
        return dict(job)


def _maybe_start_next() -> None:
    """Job queue: launch the oldest queued job when nothing is running."""
    with _lock:
        if any(j.get("status") == "running" for j in _jobs.values()):
            return
        queued = [j for j in _jobs.values() if j.get("status") == "queued"]
        if not queued:
            return
        nxt = min(queued, key=lambda j: j.get("started", 0))
        nxt["status"] = "running"
        nxt["stage"] = "script"
        nxt["message"] = "Writing the script…"
        _save_jobs()
        threading.Thread(target=_worker, args=(nxt,), daemon=True).start()


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
        try:
            premise = json.loads((d / "premise.json").read_text())
        except Exception:                       # noqa: BLE001
            premise = {}
        # collect SFX events + narration windows from the choreographies
        sfx_events, windows, off = [], [], 0.0
        n = len(script["scenes"])
        for i in range(1, n + 1):
            di = scene_len(durs.get(f"n{i}", 0.0))
            try:
                ch = json.loads((d / f"choreo{i}.json").read_text())
                water = ch.get("ground") == "water" or any(
                    pp.get("type") in ("river", "pond") for pp in ch.get("props", []))
                for a in ch.get("actors", []):
                    for act in a.get("actions", []):
                        if act.get("do") == "jump":
                            apex = (act["t"][0] + act["t"][1]) / 2
                            sfx_events.append({"type": "boing", "t": off + apex})
                            sfx_events.append({"type": "thud", "t": off + act["t"][1] + 0.02})
                            if water:
                                sfx_events.append({"type": "splash", "t": off + act["t"][1] + 0.1})
            except Exception:                   # noqa: BLE001
                pass
            nd = durs.get(f"n{i}", 0.0)
            windows.append((off + 0.4, off + 0.4 + nd / 1.10))
            off += di - 0.5
        _stage_music(d, script, premise, total=max(64.0, off + 3.0),
                     sfx_events=sfx_events, narration_windows=windows)
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
    finally:
        _maybe_start_next()


# ---------- stage 0: premise (fresh story + character every run) ----------

def _stage_premise(job: dict, p: dict, d: Path) -> dict:
    f = d / "premise.json"
    if f.exists():
        return json.loads(f.read_text())
    idea = (job.get("idea") or "").strip()
    used = [j.get("title") for j in _jobs.values() if j.get("title")]
    avoid = ("Avoid these already-used premises: " + "; ".join(used[:10]) + ". ") if used else ""
    cast_line = ""
    if (job.get("cast") or "").strip():
        cast_line = (f'The main character MUST be exactly this (keep it, do not invent '
                     f'a new one): {job["cast"].strip()}. ')
    if idea:
        task = f'Build the cartoon premise around this user idea: "{idea}". ' + cast_line
    else:
        task = ("Invent a COMPLETELY RANDOM, fresh premise: pick a surprising main "
                "character (an animal, object, or little creature — not a robot), an "
                "unexpected setting (space, jungle, kitchen, ocean floor, rooftop, "
                "library, mountain, toy shop...), a tiny problem, and a warm or funny "
                "resolution with a small twist. Vary the genre boldly. "
                + cast_line + avoid)
    prompt = f"""{task}

Return STRICT JSON only, no markdown fences:
{{"title": "...", "character": "one-sentence physical description of the main character for an artist — shape, colors, one distinguishing feature", "second_character": "one-sentence description of a side character in the story (or empty string if none)", "logline": "one sentence: what happens", "mood": "one of: cozy, playful, dreamy, adventurous, funny"}}"""
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
            data.setdefault("second_character", "")
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
- Total narration 120-140 words (~50 seconds), split across scenes (roughly 12-18 words each, closing card 3-6 words).
- EACH scene may include "dialogue": [{{"who": "main", "line": "..."}}, {{"who": "second", "line": "..."}}] — short spoken lines (max 12 words each, max 2 lines per scene) said by the characters on screen. "main" = the premise character, "second" = the side character (only if the story has one). Give dialogue to at least 4 scenes; when a scene has dialogue keep its narration to max 15 words. Write dialogue in the story language too.
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

def _tts_one(text: str, lang: str, out: Path, p: dict, cloud: "list") -> None:
    """Render one spoken line — cloud Fish TTS first, offline MMS fallback."""
    if not cloud[0]:
        _mms_tts(text, lang, out)
        return
    req = urllib.request.Request(f"{p['tts']['base_url']}/audio/speech",
        data=json.dumps({"model": p["tts"]["model"], "input": text,
                         "response_format": "mp3"}).encode(),
        headers={"Authorization": f"Bearer {p['tts']['api_key']}",
                 "Content-Type": "application/json"})
    def _tts():
        with urllib.request.urlopen(req, timeout=120) as r:
            out.write_bytes(r.read())
    try:
        _retry(_tts, tries=3, wait=4)
    except Exception as e:              # noqa: BLE001 — offline fallback
        if "429" not in str(e):
            raise
        cloud[0] = False
        print("[cartoon] tts: cloud daily cap hit — local MMS for the rest of this job",
              flush=True)
        _mms_tts(text, lang, out)


def _pitch(mp3: Path, factor: float) -> None:
    """Give a character its own voice by pitch-shifting (keeps duration)."""
    if abs(factor - 1.0) < 1e-3:
        return
    tmp = mp3.with_suffix(".tmp.mp3")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mp3),
                    "-af", f"asetrate=44100*{factor},aresample=44100,atempo={1 / factor:.5f}",
                    "-ar", "44100", "-ac", "1", "-b:a", "128k", str(tmp)], check=True)
    tmp.replace(mp3)


def _stage_tts(job: dict, p: dict, d: Path, script: dict) -> dict:
    durs = {}
    speech = {}
    n = sum(1 for sc in script["scenes"] if sc.get("narration") or sc.get("dialogue"))
    done = 0
    lang = (job.get("lang") or "en").lower()
    cloud = [True]              # once the daily cap is hit, stop wasting retries
    try:
        premise = json.loads((d / "premise.json").read_text())
        sec_desc = (premise.get("second_character") or "").lower()
    except Exception:               # noqa: BLE001
        sec_desc = ""
    sec_pitch = 0.85 if any(k in sec_desc for k in
                            ("old", "giant", "monster", "bear", "wolf", "lion",
                             "elephant", "grumpy", "deep")) else 1.18
    for i, sc in enumerate(script["scenes"], 1):
        if not (sc.get("narration") or sc.get("dialogue")):
            continue
        _update(job["id"], stage="narration", progress=0.52 + 0.13 * done / n,
                message=f"Recording voices {done+1} of {n}…")
        mp3 = d / f"narr{i}.mp3"
        segs = None
        if not mp3.exists():
            segs = []               # (file, who, gap_after, dur)
            if sc.get("narration"):
                na = d / f"narr{i}_0.mp3"
                _tts_one(sc["narration"], lang, na, p, cloud)
                segs.append([na, "main", 0.6, _probe(na)])
            for j, dl in enumerate(sc.get("dialogue") or [], 1):
                df = d / f"narr{i}_d{j}.mp3"
                _tts_one(dl["line"], lang, df, p, cloud)
                pitch = 1.06 if dl["who"] == "main" else sec_pitch
                _pitch(df, pitch)
                segs.append([df, dl["who"], 0.45, _probe(df)])
            # concat with gaps -> single scene audio
            if len(segs) == 1:
                segs[0][0].replace(mp3)
            else:
                inputs, total_in = [], []
                for k, (f, _, _, _) in enumerate(segs):
                    inputs += ["-i", str(f)]
                    total_in.append(f"[{k}:a]")
                for k, (_, _, gap, _) in enumerate(segs[:-1]):
                    sil = d / f"sil{i}_{k}.mp3"
                    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                                    "-i", "anullsrc=r=44100:cl=mono", "-t", str(gap),
                                    "-b:a", "128k", str(sil)], check=True)
                    inputs += ["-i", str(sil)]
                    total_in.append(f"[{len(segs) + k}:a]")
                order = []
                for k in range(len(segs)):
                    order.append(total_in[k])
                    if k < len(segs) - 1:
                        order.append(total_in[len(segs) + k])
                fc = "".join(order) + f"concat=n={len(order)}:v=0:a=1[a]"
                subprocess.run(["ffmpeg", "-y", "-v", "error"] + inputs +
                               ["-filter_complex", fc, "-map", "[a]",
                                "-b:a", "128k", str(mp3)], check=True)
                for f, _, _, _ in segs:
                    f.unlink(missing_ok=True)
        # speech map for lip-sync windows (durations captured before cleanup)
        if segs:
            t, lines = 0.0, []
            for f, who, gap, dur in segs:
                lines.append({"who": who, "t0": round(t, 3), "dur": round(dur, 3)})
                t += dur + gap
        else:
            lines = [{"who": "main", "t0": 0.0, "dur": durs_prev or _probe(mp3)}]
        durs[f"n{i}"] = _probe(mp3)
        if not segs:
            lines = [{"who": "main", "t0": 0.0, "dur": durs[f"n{i}"]}]
        speech[str(i)] = {"lines": lines}
        done += 1
        time.sleep(1)
    (d / "speech.json").write_text(json.dumps(speech, indent=1))
    (d / "durations.json").write_text(json.dumps(durs, indent=1))
    return durs


def _mms_tts(text: str, lang: str, out_path: Path) -> None:
    """Offline narration with the engine's Meta MMS base TTS (no cloud quota)."""
    import engine, langs
    iso = langs.MMS_ISO.get(lang)
    if not iso:
        raise RuntimeError(f"cloud TTS rate-limited and no offline voice for '{lang}'")
    engine.mms_generate(text, iso, str(out_path) + ".wav", speed=1.10)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(out_path) + ".wav",
                    "-ar", "44100", "-ac", "1", "-b:a", "128k", str(out_path)], check=True)
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
    except Exception:                       # noqa: BLE001
        character, mood = "a small round orange robot with big teal eyes", "cozy"
    # deepseek is faster + steadier at structured JSON — flip the model order
    cfg_motion = {**p["text"], "models": list(reversed(p["text"]["models"]))}

    # phase A — parallel LLM choreography (network-bound, no browser)
    raw: dict[int, dict] = {}
    errors: dict[int, str] = {}
    lens = {i: scene_len(durs.get(f"n{i}", 0.0)) for i in range(1, n + 1)}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futs = {pool.submit(cmotion.request_choreo, cfg_motion, sc, lens[i],
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
                    message=f"Blocking out scene {done} of {n}…")
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
            spk = (0.4, 0.4 + durs.get(f"n{i}", 0.0) / 1.10)
            env = None
            try:
                env = cmotion.mouth_envelope(d / f"narr{i}.mp3", lens[i])
            except Exception:               # noqa: BLE001 — sine-cycle fallback
                pass
            # per-character speak windows from the dialogue speech map
            wmap = {"main": [list(spk)], "second": []}
            try:
                sp = json.loads((d / "speech.json").read_text()).get(str(i)) or []
                wm, ws_ = [], []
                for ln in sp:
                    a = 0.4 + ln["t0"] * 1.10
                    b = 0.4 + (ln["t0"] + ln["dur"]) * 1.10
                    (ws_ if ln.get("who") == "second" else wm).append([round(a, 2), round(b, 2)])
                if wm:
                    wmap["main"] = wm
                wmap["second"] = ws_
            except Exception:               # noqa: BLE001
                pass

            def _finish(ch):
                for a in ch.get("actors", []):
                    a.setdefault("role", "main")
                    w = wmap.get(a.get("role", "main"))
                    if w:
                        a["speakWindows"] = w
                    a.pop("speaker", None)
                (d / f"choreo{i}.json").write_text(json.dumps(ch, indent=1))
                cmotion.assemble_scene_html(ch, lens[i], spk[0], spk[1], html_path, env)
                mr.validate(html_path, lens[i])
                mr.capture(html_path, lens[i], frames_dir)
                subprocess.run(["ffmpeg", "-y", "-v", "error",
                                "-i", str(frames_dir / "f00000.png"),
                                "-vf", "scale=480:-1", str(d / f"still{i}.jpg")], check=True)

            # candidate 1: the parallel result from phase A
            if i in raw:
                try:
                    _finish(raw[i])
                    ok = True
                except Exception as e:      # noqa: BLE001
                    print(f"[cartoon] scene {i}: parallel candidate rejected ({e})",
                          flush=True)
            # candidate 2: one serial retry (mimo first) — only if needed
            if not ok:
                try:
                    choreo = cmotion.request_choreo(
                        p["text"], sc, lens[i], character, spk, mood)
                    _finish(choreo)
                    ok = True
                except Exception as e:      # noqa: BLE001
                    errors[i] = str(e)
                    print(f"[cartoon] scene {i}: choreography failed: {e}", flush=True)
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


# ---------- stage 4: mood music + natural ambience ----------

def _place(sig, t, n, sr):
    import numpy as np
    i0 = int(t * sr); i1 = min(n, i0 + len(sig))
    if i0 >= n or i1 <= i0:
        return np.zeros(n)
    out = np.zeros(n)
    out[i0:i1] = sig[: i1 - i0]
    return out


def _detect_ambience(script: dict) -> str | None:
    text = " ".join((sc.get("visual") or "").lower() for sc in script.get("scenes", []))
    if any(k in text for k in ("rain", "storm", "drizzle")):
        return "rain"
    if any(k in text for k in ("snow", "winter", "blizzard")):
        return "wind"
    if any(k in text for k in ("beach", "ocean", "sea ", "waves", "river", "pond", "lake", "boat")):
        return "waves"
    if any(k in text for k in ("night", "moon", "star", "firefl")):
        return "crickets"
    if any(k in text for k in ("garden", "forest", "tree", "jungle", "flower", "park", "meadow", "village", "farm")):
        return "birds"
    if any(k in text for k in ("room", "kitchen", "indoor", "library", "house", "home")):
        return None
    return "birds"


def _stage_music(d: Path, script: dict | None = None, premise: dict | None = None,
                 total: float = 64.0, sfx_events: list | None = None,
                 narration_windows: list | None = None) -> None:
    wav = d / "music.wav"
    if wav.exists():
        return
    import numpy as np
    mood = (premise or {}).get("mood", "cozy").lower()
    amb = _detect_ambience(script or {})
    SR = 44100
    n = int(SR * total)
    rng = np.random.default_rng(42)
    audio = np.zeros(n)

    def pluck(freq, dur, vol):
        N = int(SR * dur)
        buf_n = int(SR / freq)
        buf = rng.random(buf_n) * 2 - 1
        out = np.zeros(N)
        for j in range(N):
            k = j % buf_n
            out[j] = buf[k]
            buf[k] = 0.996 * 0.5 * (buf[k] + buf[(k + 1) % buf_n])
        return out * np.exp(-np.linspace(0, 4.5, N)) * vol

    def tick(vol):  # soft percussion
        N = int(SR * 0.03)
        return rng.random(N) * np.exp(-np.linspace(0, 9, N)) * vol

    # ---- music by mood ----
    if mood in ("playful", "funny"):
        step, notes_hz, bass_every, perc_every = 0.34, \
            [587.33, 659.25, 783.99, 880.00, 1046.5, 1174.7], 8, 2
    elif mood == "adventurous":
        step, notes_hz, bass_every, perc_every = 0.46, \
            [440.0, 523.25, 587.33, 659.25, 783.99, 880.0], 4, 2
    else:  # cozy / dreamy lullaby
        step, notes_hz, bass_every, perc_every = 1.05, \
            [523.25, 587.33, 659.25, 783.99, 880.00, 1046.50], 4, 0
    note_len = min(1.6, step * 1.9)
    mi = 0; t = 0.0
    while t < total - 2:
        if mi % 8 != 7:
            audio += _place(pluck(notes_hz[(mi * 3) % len(notes_hz)], note_len, 0.5), t, n, SR)
        if mi % bass_every == 0:
            audio += _place(pluck(notes_hz[0] / 2, note_len * 1.6, 0.30), t, n, SR)
        if perc_every and mi % perc_every == 0:
            audio += _place(tick(0.16), t, n, SR)
        t += step; mi += 1
    audio /= max(1e-9, np.abs(audio).max())
    audio *= 0.30

    # ---- ambience layer ----
    ambn = np.zeros(n)
    if amb == "birds":
        for _ in range(int(total * 2.2)):
            tt = float(rng.uniform(0.3, total - 0.6))
            f0, f1 = float(rng.uniform(2400, 3300)), float(rng.uniform(1800, 2500))
            N = int(SR * rng.uniform(0.07, 0.16))
            chirp = np.sin(2 * np.pi * np.linspace(f0, f1, N) * np.linspace(0, 0.13, N)) \
                * np.hanning(N) * 0.16
            ambn += _place(chirp, tt, n, SR)
    elif amb == "crickets":
        t = 0.0
        while t < total - 1:
            burst = int(SR * rng.uniform(0.4, 0.9))
            tt = np.arange(burst) / SR
            ambn += _place(np.sin(2 * np.pi * 4300 * tt)
                           * (0.5 + 0.5 * np.sign(np.sin(2 * np.pi * 26 * tt)))
                           * np.hanning(burst) * 0.055, t, n, SR)
            t += burst / SR + float(rng.uniform(0.15, 0.6))
    elif amb == "waves":
        noise = rng.standard_normal(n)
        k = np.hanning(int(SR * 0.35)); k /= k.sum()
        slow = np.convolve(noise, k, mode="same")
        env = 0.5 + 0.5 * np.sin(2 * np.pi * total * 0.0 / 9 * np.linspace(0, 1, n) * 9)
        ambn += slow * env * 0.16
    elif amb == "rain":
        ambn += rng.standard_normal(n) * 0.045
        k = np.hanning(int(SR * 0.004)); k /= k.sum()
        ambn = np.convolve(ambn, k, mode="same") * 1.6
    elif amb == "wind":
        noise = rng.standard_normal(n)
        k = np.hanning(int(SR * 0.6)); k /= k.sum()
        ambn += np.convolve(noise, k, mode="same") * (0.5 + 0.5 * np.sin(np.linspace(0, 6 * np.pi, n))) * 0.10
    audio += ambn

    # ---- sound effects at action moments (jump apex boing + landing thud) ----
    def sfx_boing(vol=0.5):
        N = int(SR * 0.38)
        tt = np.arange(N) / SR
        f = 420 * np.exp(-tt * 6) + 130
        return np.sin(2 * np.pi * f * tt) * np.exp(-tt * 9) * vol

    def sfx_thud(vol=0.6):
        N = int(SR * 0.14)
        tt = np.arange(N) / SR
        return np.sin(2 * np.pi * 84 * tt) * np.exp(-tt * 26) * vol

    def sfx_splash(vol=0.35):
        N = int(SR * 0.42)
        noise = rng.standard_normal(N)
        k = np.hanning(int(SR * 0.02)); k /= k.sum()
        return np.convolve(noise, k, mode="same") * np.exp(-np.linspace(0, 7, N)) * vol

    for ev in (sfx_events or []):
        if ev.get("type") == "boing":
            audio += _place(sfx_boing(), ev["t"], n, SR)
        elif ev.get("type") == "thud":
            audio += _place(sfx_thud(), ev["t"], n, SR)
        elif ev.get("type") == "splash":
            audio += _place(sfx_splash(), ev["t"], n, SR)

    # ---- duck music under narration windows ----
    for w0, w1 in (narration_windows or []):
        a, b = max(0.0, w0 - 0.3), min(total, w1 + 0.3)
        i0, i1 = int(a * SR), int(b * SR)
        if i1 > i0:
            fade = int(0.35 * SR)
            duck = np.ones(i1 - i0)
            duck[:fade] *= np.linspace(1, 0.38, fade)
            duck[-fade:] *= np.linspace(0.38, 1, fade)
            audio[i0:i1] *= duck

    audio /= max(1e-9, np.abs(audio).max())
    audio *= 0.42
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


def gallery(limit: int = 24) -> list[dict]:
    done = [j for j in _jobs.values() if j.get("status") == "done"]
    done.sort(key=lambda j: j.get("finished", 0), reverse=True)
    return [{"id": j["id"], "title": j.get("title", "Cartoon"),
             "duration": j.get("duration"), "finished": j.get("finished"),
             "client": j.get("client", "")} for j in done[:limit]]


def job_still(jid: str, scene: int) -> Path | None:
    p = JOBS_DIR / f"job_{jid}" / f"still{scene}.jpg"
    return p if p.exists() else None


def job_stills(jid: str) -> list[int]:
    d = JOBS_DIR / f"job_{jid}"
    if not d.exists():
        return []
    out = []
    for i in range(1, 10):
        if (d / f"still{i}.jpg").exists():
            out.append(i)
    return out


def admin_stats() -> dict:
    jobs = [{"id": j["id"], "client": j.get("client", ""), "status": j.get("status"),
             "stage": j.get("stage"), "title": j.get("title"),
             "mode": j.get("mode"), "lang": j.get("lang"),
             "started": j.get("started"), "finished": j.get("finished"),
             "error": (j.get("error") or "")[:120]}
            for j in _jobs.values()]
    jobs.sort(key=lambda j: j.get("started") or 0, reverse=True)
    return {"jobs": jobs[:40], "quota": _quota_map(),
            "providers": PROVIDERS_FILE.exists()}


def reroll_scene(jid: str, scene: int, p: dict) -> dict:
    """Regenerate ONE scene (choreography + frames + clip) and re-cut the video."""
    job = _jobs.get(jid)
    if not job or job.get("status") not in ("done", "error"):
        raise RuntimeError("can only re-roll finished cartoons")
    d = JOBS_DIR / f"job_{jid}"
    script_f, durs_f = d / "script.json", d / "durations.json"
    if not script_f.exists() or not durs_f.exists():
        raise RuntimeError("job data missing — cannot re-roll")
    script = json.loads(script_f.read_text())
    durs = json.loads(durs_f.read_text())
    n = len(script["scenes"])
    if not (1 <= scene <= n):
        raise ValueError(f"scene must be 1..{n}")
    try:
        premise = json.loads((d / "premise.json").read_text())
        character, mood = premise["character"], premise.get("mood", "cozy")
    except Exception:                       # noqa: BLE001
        character, mood = "a small round orange robot with big teal eyes", "cozy"
    sc = script["scenes"][scene - 1]
    nd = durs.get(f"n{scene}", 0.0)
    di = scene_len(nd)
    spk = (0.4, 0.4 + nd / 1.10)
    for name in (f"clip{scene}.mp4", f"scene{scene}.html", f"still{scene}.jpg",
                 "cartoon.mp4", f"choreo{scene}.json"):
        (d / name).unlink(missing_ok=True)
    frames_dir = d / f"frames{scene}"
    if frames_dir.exists():
        subprocess.run(["rm", "-rf", str(frames_dir)], check=False)
    _update(jid, status="running", stage="animation", progress=0.5,
            message=f"Re-rolling scene {scene}…", error=None)

    def worker():
        try:
            import cartoon_motion as cmotion
            with cmotion.MotionRenderer() as mr:
                ok = False
                try:
                    choreo = cmotion.request_choreo(p["text"], sc, di, character, spk, mood)
                    env = None
                    try:
                        env = cmotion.mouth_envelope(d / f"narr{scene}.mp3", di)
                    except Exception:       # noqa: BLE001
                        pass
                    (d / f"choreo{scene}.json").write_text(json.dumps(choreo, indent=1))
                    html = cmotion.assemble_scene_html(choreo, di, spk[0], spk[1],
                                                       d / f"scene{scene}.html", env)
                    mr.validate(html, di)
                    mr.capture(html, di, frames_dir)
                    subprocess.run(["ffmpeg", "-y", "-v", "error",
                                    "-i", str(frames_dir / "f00000.png"),
                                    "-vf", "scale=480:-1", str(d / f"still{scene}.jpg")],
                                   check=True)
                    ok = True
                except Exception as e:      # noqa: BLE001 — image fallback
                    print(f"[cartoon] re-roll scene {scene}: {e} — image fallback", flush=True)
                if not ok:
                    png = d / f"scene{scene}.png"
                    png.unlink(missing_ok=True)
                    _gen_image(p, f"{sc['visual']}. Character: {character}. {STYLE_BASE}", png)
                subprocess.run(["ffmpeg", "-y", "-v", "error",
                                "-i", str(d / f"scene{scene}.png"),
                                "-vf", "scale=480:-1", str(d / f"still{scene}.jpg")],
                               check=True)
                _stage_render(job, d, script, durs)
                _update(jid, status="done", stage="done", progress=1.0,
                        message=f"Scene {scene} re-rolled!", duration=round(_probe(d / "cartoon.mp4"), 1),
                        finished=time.time())
        except Exception as e:              # noqa: BLE001
            _update(jid, status="error", message=str(e)[:300], error=str(e)[:300],
                    finished=time.time())
        finally:
            _maybe_start_next()

    threading.Thread(target=worker, daemon=True).start()
    return {"id": jid, "scene": scene, "status": "running"}


_load_jobs()
JOBS_DIR.mkdir(parents=True, exist_ok=True)
