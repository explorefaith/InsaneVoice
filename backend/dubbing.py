"""InsaneVoice — Dubbing Studio.

video/audio  ->  transcribe (vosk, word timings)  ->  editable segments
             ->  re-voice each segment with a cloned voice (time-fit via
                 gentle atempo when a take overruns its slot)
             ->  mux back onto the original video (video stream copied).

Same-language re-voicing: the performance timing is preserved, the voice is
yours. Cross-language translation needs a translation model — deliberately
out of scope for a fully-local, free tool.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import config
import stt
from storage import new_id, now


def extract_audio(video_path: Path, out_wav: Path) -> float:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(video_path),
         "-vn", "-ar", "16000", "-ac", "1", str(out_wav)],
        check=True, capture_output=True, timeout=1800)
    import soundfile as sf
    info = sf.info(str(out_wav))
    return float(info.duration)


def _sentence_segments(words: list[dict], max_len: float = 13.0) -> list[dict]:
    """Group word timings into dubbing-friendly segments."""
    segments: list[dict] = []
    cur: list[dict] = []

    def flush():
        if not cur:
            return
        text = " ".join(w["word"] for w in cur)
        # punctuation cleanup from vosk
        segments.append({
            "start": round(cur[0]["start"], 3),
            "end": round(cur[-1]["end"], 3),
            "text": text[0].upper() + text[1:] if text else text,
        })
        cur.clear()

    for w in words:
        cur.append(w)
        gap = (w["start"] - cur[-2]["end"]) if len(cur) > 1 else 0
        dur = w["end"] - cur[0]["start"]
        if (dur >= max_len or w["word"].endswith((".", "!", "?"))
                or (gap > 0.6 and len(cur) >= 3)):
            flush()
    flush()
    return segments


def ingest(video_path: Path, lang: str = "en-us", progress=None) -> dict:
    """-> {duration, segments:[{start,end,text}], srt, media:{video,audio}}"""
    uid = new_id("dub")
    workdir = config.DATA_DIR / "dubbing" / uid
    workdir.mkdir(parents=True, exist_ok=True)
    audio = workdir / "source.wav"
    duration = extract_audio(video_path, audio)
    result = stt.transcribe(audio, lang=lang, progress=progress)
    segments = _sentence_segments(result["words"])
    return {
        "id": uid,
        "duration": duration,
        "segments": segments,
        "srt": result["srt"],
        "text": result["text"],
        "media": {"video": str(video_path), "audio": str(audio)},
        "created_at": now(),
    }


def revoice(dub: dict, assignments: list[dict], out_name: str | None = None,
            progress=None) -> dict:
    """assignments: [{index, voice_id, text?, tau?, speed?}] -> new track + mux.

    Segment slot = its original timing. If the take overruns the slot by >8%,
    it is gently time-compressed (max 1.28x) to stay in sync.
    """
    import soundfile as sf
    import engine
    from storage import get_voice

    workdir = config.DATA_DIR / "dubbing" / dub["id"]
    parts = []
    report = []
    segs = dub["segments"]
    assignments_by_idx = {a["index"]: a for a in assignments}

    total = len(segs)
    for i, seg in enumerate(segs):
        a = assignments_by_idx.get(i)
        if not a or not a.get("voice_id"):
            report.append({"index": i, "status": "skipped"})
            if progress:
                progress(i / total)
            continue
        voice = get_voice(a["voice_id"])
        if not voice:
            report.append({"index": i, "status": "voice_missing"})
            continue
        text = (a.get("text") or seg["text"]).strip()
        slot = seg["end"] - seg["start"]
        raw = workdir / f"seg{i:03d}_raw.wav"
        engine.generate(text, voice["se_path"], raw,
                        speed=float(a.get("speed", 1.0)),
                        tau=float(a.get("tau", 0.3)),
                        accent=a.get("accent"), lang=a.get("lang", "en"))
        dur = len(sf.read(str(raw), dtype="float32")[0]) / 22050
        speed_fit = 1.0
        if dur > slot * 1.08 and dur > 0:
            speed_fit = min(1.28, dur / slot)
        fitted = workdir / f"seg{i:03d}.wav"
        if speed_fit > 1.001:
            t = speed_fit
            chain = []
            v = t
            while v > 2.0:
                chain.append("atempo=2.0"); v /= 2.0
            chain.append(f"atempo={v:.4f}")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw),
                            "-af", ",".join(chain), str(fitted)],
                           check=True, capture_output=True)
            raw.unlink(missing_ok=True)
        else:
            fitted = raw
        parts.append((seg["start"], fitted))
        report.append({"index": i, "status": "ok", "fit": round(speed_fit, 3),
                       "take_dur": round(dur, 2), "slot": round(slot, 2)})
        if progress:
            progress((i + 1) / total)

    # assemble the new track at original timing
    track = workdir / "dubbed.wav"
    if not parts:
        raise RuntimeError("No segments were assigned a voice.")
    total_dur = dub["duration"] + 1.0
    args = ["ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i",
            f"anullsrc=r=22050:cl=mono:d={total_dur:.3f}"]
    for i, (start, f) in enumerate(parts):
        args += ["-i", str(f)]
    fc = "[0:a]anull[base];"
    for i, (start, f) in enumerate(parts):
        fc += f"[{i + 1}:a]adelay={int(start * 1000)}:all=1[d{i}];"
    fc += "[base]" + "".join(f"[d{i}]" for i in range(len(parts)))
    fc += f"amix=inputs={len(parts) + 1}:duration=first:normalize=0[out]"
    args += ["-filter_complex", fc, "-map", "[out]", str(track)]
    subprocess.run(args, check=True, capture_output=True, timeout=1800)

    out_name = out_name or f"dubbed_{dub['id']}.wav"
    final_audio = config.OUTPUT_DIR / out_name
    track.replace(final_audio)

    result = {"audio": {"file": out_name, "url": f"/api/audio/output/{out_name}"},
              "report": report}

    # optional mux with the source video
    video = dub["media"].get("video")
    if video and Path(video).exists() and Path(video).suffix.lower() in (
            ".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"):
        vid_out = config.OUTPUT_DIR / out_name.replace(".wav", ".mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(video),
             "-i", str(final_audio), "-map", "0:v:0", "-map", "1:a:0",
             "-c:v", "copy", "-c:a", "aac", "-shortest", str(vid_out)],
            check=True, capture_output=True, timeout=3600)
        result["video"] = {"file": vid_out.name,
                           "url": f"/api/agent/video/{vid_out.name}"}
    return result
