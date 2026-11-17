"""InsaneVoice — Director's Studio (long-form projects).

A project is a script cut into logical chunks (paragraphs / sentences).
For every chunk the engine renders several takes with subtle performance
variation; the director picks the best or re-renders just that chunk.
Export stitches the selected takes — optionally noise-isolated — into one
audiobook / podcast file.
"""
from __future__ import annotations

import json
import re
import subprocess
import threading
import time
from pathlib import Path

import config
from storage import new_id, now

PROJECTS_DIR = config.DATA_DIR / "projects"
_lock = threading.RLock()


def _pdir(pid: str) -> Path:
    d = PROJECTS_DIR / pid
    d.mkdir(parents=True, exist_ok=True)
    return d


def _pfile(pid: str) -> Path:
    return _pdir(pid) / "project.json"


def _read(pid: str) -> dict | None:
    try:
        return json.loads(_pfile(pid).read_text(encoding="utf-8"))
    except Exception:
        return None


def _write(proj: dict) -> None:
    _pfile(proj["id"]).write_text(json.dumps(proj, ensure_ascii=False, indent=1),
                                  encoding="utf-8")


def chunk_text(text: str) -> list[str]:
    """Split into paragraph chunks; huge paragraphs fall to sentences."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    chunks: list[str] = []
    for p in paras:
        if len(p) <= 420:
            chunks.append(p)
            continue
        sents = re.split(r"(?<=[.!?])\s+", p)
        buf = ""
        for s in sents:
            if len(buf) + len(s) > 380 and buf:
                chunks.append(buf.strip())
                buf = s
            else:
                buf = (buf + " " + s).strip()
        if buf:
            chunks.append(buf.strip())
    return chunks or ([text.strip()] if (text or "").strip() else [])


# ---------------- CRUD ----------------

def create(title: str, voice_id: str, script: str, lang: str = "en",
           accent: str | None = None, speed: float = 1.0, tau: float = 0.3) -> dict:
    pid = new_id("prj")
    proj = {
        "id": pid, "title": (title or "Untitled project")[:80],
        "voice_id": voice_id, "lang": lang, "accent": accent,
        "speed": speed, "tau": tau, "created_at": now(),
        "chunks": [{"id": new_id("chk"), "text": c, "takes": [], "selected": None}
                   for c in chunk_text(script)],
    }
    _write(proj)
    return proj


def list_projects() -> list[dict]:
    out = []
    if PROJECTS_DIR.exists():
        for d in PROJECTS_DIR.iterdir():
            p = _read(d.name)
            if p:
                out.append(p)
    return sorted(out, key=lambda x: x["created_at"], reverse=True)


def get(pid: str) -> dict | None:
    return _read(pid)


def delete(pid: str) -> bool:
    with _lock:
        if not _pfile(pid).exists():
            return False
    import shutil
    shutil.rmtree(_pdir(pid), ignore_errors=True)
    return True


def update_chunk(pid: str, chunk_id: str, patch: dict) -> dict | None:
    with _lock:
        proj = _read(pid)
        if not proj:
            return None
        for c in proj["chunks"]:
            if c["id"] == chunk_id:
                if "text" in patch:
                    c["text"] = str(patch["text"])[:4000]
                if "selected" in patch:
                    c["selected"] = patch["selected"]
                _write(proj)
                return c
    return None


def add_chunk(pid: str, text: str, after_id: str | None = None) -> dict | None:
    with _lock:
        proj = _read(pid)
        if not proj:
            return None
        chunk = {"id": new_id("chk"), "text": text[:4000], "takes": [], "selected": None}
        idx = next((i for i, c in enumerate(proj["chunks"]) if c["id"] == after_id), None)
        if idx is None:
            proj["chunks"].append(chunk)
        else:
            proj["chunks"].insert(idx + 1, chunk)
        _write(proj)
        return chunk


def delete_chunk(pid: str, chunk_id: str) -> bool:
    with _lock:
        proj = _read(pid)
        if not proj:
            return False
        before = len(proj["chunks"])
        proj["chunks"] = [c for c in proj["chunks"] if c["id"] != chunk_id]
        if len(proj["chunks"]) == before:
            return False
        _write(proj)
        return True


# ---------------- takes ----------------

def gen_take(pid: str, chunk_id: str, variant: int = 0) -> dict | None:
    """Render one take. variant jitters speed/tau for natural alternatives."""
    import soundfile as sf
    import engine, dna

    proj = _read(pid)
    if not proj:
        return None
    chunk = next((c for c in proj["chunks"] if c["id"] == chunk_id), None)
    if not chunk:
        return None
    voice = None
    from storage import get_voice
    voice = get_voice(proj["voice_id"])
    if not voice:
        raise RuntimeError("Project voice no longer exists.")

    speed = float(proj["speed"]) * (1.0 + variant * 0.035)
    tau = min(0.95, float(proj["tau"]) + variant * 0.05)
    tid = new_id("tk")
    out = _pdir(pid) / f"{chunk_id}_{tid}.wav"
    engine.generate(chunk["text"], voice["se_path"], out,
                    speed=speed, tau=tau, accent=proj.get("accent"),
                    lang=proj.get("lang", "en"))
    info = sf.info(str(out))
    d = dna.analyze(str(out))
    take = {"id": tid, "file": out.name, "variant": variant,
            "duration": round(info.duration, 2), "f0": d["f0_median"],
            "created_at": now()}
    with _lock:
        proj = _read(pid)
        chunk = next((c for c in proj["chunks"] if c["id"] == chunk_id), None)
        chunk["takes"].append(take)
        if chunk["selected"] is None:
            chunk["selected"] = tid
        _write(proj)
    return take


def delete_take(pid: str, chunk_id: str, take_id: str) -> bool:
    with _lock:
        proj = _read(pid)
        if not proj:
            return False
        chunk = next((c for c in proj["chunks"] if c["id"] == chunk_id), None)
        if not chunk:
            return False
        chunk["takes"] = [t for t in chunk["takes"] if t["id"] != take_id]
        if chunk["selected"] == take_id:
            chunk["selected"] = chunk["takes"][0]["id"] if chunk["takes"] else None
        (_pdir(pid) / f"{chunk_id}_{take_id}.wav").unlink(missing_ok=True)
        _write(proj)
        return True


# ---------------- export ----------------

def export_project(pid: str, gap: float = 0.45, isolate: bool = False,
                   fmt: str = "wav") -> dict:
    proj = _read(pid)
    if not proj:
        raise RuntimeError("Project not found.")
    selected = [(c, t) for c in proj["chunks"]
                for t in c["takes"] if t["id"] == c["selected"]]
    if not selected:
        raise RuntimeError("No takes selected yet — generate takes first.")

    tmp = _pdir(pid) / f"export_{new_id('x')}"
    tmp.mkdir(exist_ok=True)
    parts = []
    for i, (c, t) in enumerate(selected):
        src = _pdir(pid) / t["file"]
        dst = tmp / f"p{i:03d}.wav"
        af = ("afftdn=nr=10:nf=-25,highpass=f=65,speechnorm=e=6:r=0.0005:l=1"
              if isolate else "anull")
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
             "-af", af, "-ar", "22050", "-ac", "1", str(dst)],
            check=True, capture_output=True)
        parts.append(dst)

    # build [part, silence, part, silence..., part] concat graph
    args = ["ffmpeg", "-y", "-loglevel", "error"]
    silence = f"anullsrc=r=22050:cl=mono:d={gap}"
    for p in parts:
        args += ["-i", str(p)]
    for i in range(len(parts) - 1):
        args += ["-f", "lavfi", "-i", silence]
    fc = ""
    # interleave: 0, n0, 1, n1, ... where n = len(parts), silences appended after
    nparts = len(parts)
    for i in range(nparts):
        fc += f"[{i}:a]"
        if i < nparts - 1:
            fc += f"[{nparts + i}:a]"
    fc += f"concat=n={nparts * 2 - 1}:v=0:a=1[out]"
    out_name = f"{re.sub(r'[^\w-]+', '_', proj['title'])}.{fmt}"
    out = config.OUTPUT_DIR / out_name
    args += ["-filter_complex", fc, "-map", "[out]"]
    if fmt == "mp3":
        args += ["-b:a", "192k"]
    args += [str(out)]
    subprocess.run(args, check=True, capture_output=True)

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    import soundfile as sf
    info = sf.info(str(out))
    return {"file": out.name, "url": f"/api/audio/output/{out.name}",
            "duration": round(info.duration, 2), "chunks": len(selected)}
