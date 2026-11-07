"""InsaneVoice — motion graphics engine.

Renders branded animated scenes to mp4 with PIL frames + ffmpeg. This is
the local "motion model": when no video-generation provider is connected,
the Agent Studio still produces a polished, on-brand video — animated
titles, points, quotes, Ken-Burns images and an audio-synced waveform.

Visual language = the approved C1 identity: warm paper, ink type, one
vermillion peak. No gradients-glow-purple template nonsense.
"""
from __future__ import annotations

import math
import subprocess
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

PAPER = (244, 239, 230)
PAPER2 = (236, 229, 216)
INK = (26, 23, 18)
INK2 = (74, 68, 56)
INK3 = (122, 114, 99)
VERM = (201, 67, 43)
LINE = (216, 207, 190)

W, H = 1280, 720
FPS = 30
FONT_DIR = Path("C:/Windows/Fonts")


def _font(name: str, size: int):
    try:
        return ImageFont.truetype(str(FONT_DIR / name), size)
    except Exception:
        return ImageFont.load_default()


def SERIF(s):
    return _font("georgia.ttf", s)


def SERIF_I(s):
    return _font("georgiab.ttf", s)


def SANS(s, bold=False):
    return _font("seguisb.ttf" if bold else "segoeui.ttf", s)


def _ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def _wrap(draw, text, font, max_w):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= max_w:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def audio_peaks(wav_path: Path, frames: int) -> list[float]:
    """RMS envelope per frame for waveform bars."""
    try:
        with wave.open(str(wav_path), "rb") as wf:
            n = wf.getnframes()
            raw = wf.readframes(n)
        import array
        a = array.array("h")
        a.frombytes(raw)
        step = max(1, len(a) // frames)
        peaks = []
        for i in range(frames):
            seg = a[i * step:(i + 1) * step:16]
            if not seg:
                peaks.append(0.0)
                continue
            rms = math.sqrt(sum(x * x for x in seg) / len(seg)) / 32768
            peaks.append(min(1.0, rms * 2.6))
        return peaks
    except Exception:
        return [0.0] * frames


# ---------------- scene painters ----------------

def _bg(t, palette=(PAPER, PAPER2)):
    """Base paper with a slow diagonal tone drift."""
    img = Image.new("RGB", (W, H), palette[0])
    d = ImageDraw.Draw(img)
    # subtle drifting block
    off = int((math.sin(t * 0.35) * 0.5 + 0.5) * 90)
    d.rectangle([W - 380 + off, H - 210, W + 60, H], fill=palette[1])
    d.rectangle([-60 + off * 0.4, -40, 210 + off * 0.4, 150], fill=palette[1])
    return img


def _wordmark_footer(d, frame_no, total_frames):
    d.text((W - 46, H - 44), "InsaneVoice", font=SANS(17, bold=True),
           fill=INK3, anchor="rs")
    d.ellipse([W - 40, H - 58, W - 26, H - 44], fill=VERM)


def _progress_top(d, p):
    d.rectangle([0, 0, W, 5], fill=LINE)
    d.rectangle([0, 0, int(W * p), 5], fill=VERM)


def _wavebars(d, peaks, frame, bottom=H - 96, max_h=64, n_bars=72):
    if not peaks:
        return
    step = max(1, len(peaks) // n_bars)
    bw = W / n_bars
    mid = bottom
    for i in range(n_bars):
        p = peaks[min(i * step, len(peaks) - 1)]
        h = max(3, p * max_h)
        x = i * bw + bw * 0.22
        col = VERM if abs(i - n_bars // 2) < 1 else INK
        d.rounded_rectangle([x, mid - h / 2, x + bw * 0.56, mid + h / 2],
                            radius=bw * 0.28, fill=col)


def paint_title(img, scene, t_norm, frame_peaks):
    d = ImageDraw.Draw(img)
    pad = 90
    # big serif title, word-by-word rise
    lines = _wrap(d, scene.get("text", ""), SERIF_I(72), W - pad * 2)
    lh = 86
    total = len(lines) * lh
    y0 = H / 2 - total / 2 - 30
    words_pos = []
    for li, line in enumerate(lines):
        words_pos.append((line, y0 + li * lh))
    for li, (line, y) in enumerate(words_pos):
        a = _ease((t_norm - li * 0.06) / 0.35)
        if a <= 0:
            continue
        alpha = int(255 * min(1, a))
        color = tuple(int(INK[i] * a + PAPER[i] * (1 - a)) for i in range(3))
        d.text((pad, y + (1 - a) * 26), line, font=SERIF_I(72), fill=color)
    sub = scene.get("sub")
    if sub:
        sa = _ease((t_norm - 0.45) / 0.4)
        if sa > 0:
            color = tuple(int(INK2[i] * sa + PAPER[i] * (1 - sa)) for i in range(3))
            d.text((pad + 4, y0 + total + 16), sub, font=SANS(26), fill=color)
    if frame_peaks:
        wa = _ease((t_norm - 0.25) / 0.3)
        if wa > 0.02:
            scaled = [p * wa for p in frame_peaks]
            _wavebars(d, scaled, t_norm)
    _progress_top(d, t_norm)
    _wordmark_footer(d, t_norm, 1)


def paint_points(img, scene, t_norm, frame_peaks):
    d = ImageDraw.Draw(img)
    pad = 100
    title = scene.get("text", "")
    ta = _ease(t_norm / 0.3)
    color = tuple(int(INK[i] * ta + PAPER[i] * (1 - ta)) for i in range(3))
    d.text((pad, 84), title, font=SERIF_I(54), fill=color)
    d.rectangle([pad, 156, pad + 64 * ta, 160], fill=VERM)
    points = scene.get("points") or []
    y = 220
    for i, pt in enumerate(points):
        a = _ease((t_norm - 0.25 - i * 0.12) / 0.3)
        if a <= 0:
            y += 92
            continue
        cy = y + (1 - a) * 22
        color = tuple(int(INK[i2] * a + PAPER[i2] * (1 - a)) for i2 in range(3))
        # index square
        d.rectangle([pad, cy - 4, pad + 34, cy + 30], fill=INK if a > 0.9 else LINE)
        d.text((pad + 10, cy - 2), str(i + 1), font=SANS(20, bold=True),
               fill=PAPER if a > 0.9 else INK3)
        lines = _wrap(d, pt, SANS(30), W - pad * 2 - 60)
        for j, ln in enumerate(lines):
            d.text((pad + 56, cy + j * 40), ln, font=SANS(30), fill=color)
        y += 92 * (len(lines)) if len(lines) > 1 else 92
    if frame_peaks:
        wa = _ease((t_norm - 0.2) / 0.3)
        if wa > 0.02:
            _wavebars(d, [p * wa for p in frame_peaks], t_norm)
    _progress_top(d, t_norm)
    _wordmark_footer(d, t_norm, 1)


def paint_quote(img, scene, t_norm, frame_peaks):
    d = ImageDraw.Draw(img)
    pad = 130
    a = _ease(t_norm / 0.4)
    d.text((pad - 26, 130), "\u201C", font=SERIF(190),
           fill=tuple(int(VERM[i] * a + PAPER[i] * (1 - a)) for i in range(3)))
    lines = _wrap(d, scene.get("text", ""), SERIF(52), W - pad * 2)
    lh = 74
    y0 = H / 2 - len(lines) * lh / 2
    for li, line in enumerate(lines):
        aa = _ease((t_norm - li * 0.05) / 0.35)
        if aa <= 0:
            continue
        color = tuple(int(INK[i] * aa + PAPER[i] * (1 - aa)) for i in range(3))
        d.text((pad, y0 + li * lh + (1 - aa) * 20), line, font=SERIF(52), fill=color)
    who = scene.get("sub")
    if who:
        wa = _ease((t_norm - 0.5) / 0.3)
        if wa > 0:
            d.text((pad + 4, y0 + len(lines) * lh + 8), "— " + who,
                   font=SANS(24), fill=tuple(int(INK3[i] * wa + PAPER[i] * (1 - wa)) for i in range(3)))
    _progress_top(d, t_norm)
    _wordmark_footer(d, t_norm, 1)


def paint_wave(img, scene, t_norm, frame_peaks):
    """Full-screen waveform moment (nice under narration bridges)."""
    d = ImageDraw.Draw(img)
    a = _ease(t_norm / 0.25)
    title = scene.get("text")
    if title:
        ta = _ease((t_norm - 0.1) / 0.3)
        color = tuple(int(INK[i] * ta + PAPER[i] * (1 - ta)) for i in range(3))
        d.text((W / 2, 150), title, font=SERIF_I(46), fill=color, anchor="ma")
    _wavebars(d, [p * a for p in frame_peaks], t_norm, bottom=H / 2 + 40, max_h=210, n_bars=110)
    _progress_top(d, t_norm)
    _wordmark_footer(d, t_norm, 1)


def paint_image(img, scene, t_norm, frame_peaks, image_path: Path | None):
    """Ken Burns over a still (generated image or attachment)."""
    d = ImageDraw.Draw(img)
    if image_path and Path(image_path).exists():
        try:
            still = Image.open(image_path).convert("RGB")
            # gentle zoom 1.0 -> 1.08
            z = 1.0 + 0.08 * t_norm
            sw, sh = still.size
            cw, ch = int(W / z), int(H / z)
            x0 = min(max(0, (sw - cw) // 2), max(0, sw - cw))
            y0 = min(max(0, (sh - ch) // 2), max(0, sh - ch))
            still = still.crop((x0, y0, x0 + cw, y0 + ch)).resize((W, H), Image.LANCZOS)
            img.paste(still, (0, 0))
            # paper veil for legibility
            veil = Image.new("RGBA", (W, H), (244, 239, 230, 0))
            dv = ImageDraw.Draw(veil)
            va = int(120 * min(1, t_norm * 3))
            dv.rectangle([0, H - 210, W, H], fill=(244, 239, 230, va))
            dv.rectangle([0, 0, W, 90], fill=(244, 239, 230, va))
            img = Image.alpha_composite(img.convert("RGBA"), veil).convert("RGB")
        except Exception:
            pass
    d = ImageDraw.Draw(img)
    cap = scene.get("text")
    if cap:
        aa = _ease((t_norm - 0.15) / 0.35)
        lines = _wrap(d, cap, SERIF_I(44), W - 180)
        y = H - 80 - len(lines) * 56
        for li, line in enumerate(lines):
            color = tuple(int(INK[i] * aa + PAPER[i] * (1 - aa)) for i in range(3))
            d.text((90, y + li * 56 + (1 - aa) * 18), line, font=SERIF_I(44), fill=color)
    _progress_top(d, t_norm)
    _wordmark_footer(d, t_norm, 1)


def paint_end(img, scene, t_norm, frame_peaks):
    d = ImageDraw.Draw(img)
    # giant mark bars, breathing
    heights = [70, 128, 100, 190, 148, 252, 336, 300, 452, 380, 262, 210, 160, 122, 82]
    n = len(heights)
    bw, gap = 14, 16
    total = n * bw + (n - 1) * gap
    x0 = (W - total) / 2
    breath = 0.86 + 0.14 * math.sin(t_norm * math.pi * 2)
    for i, h in enumerate(heights):
        hh = h * 0.62 * breath * _ease(min(1, t_norm * 2.2))
        x = x0 + i * (bw + gap)
        col = VERM if i == 8 else INK
        d.rounded_rectangle([x, H / 2 - hh / 2 + 40, x + bw, H / 2 + hh / 2 + 40],
                            radius=bw / 2, fill=col)
    a = _ease((t_norm - 0.25) / 0.35)
    if a > 0:
        d.text((W / 2, H / 2 + 150), scene.get("text") or "InsaneVoice",
               font=SERIF_I(40), fill=tuple(int(INK[i] * a + PAPER[i] * (1 - a)) for i in range(3)),
               anchor="ma")
    _wordmark_footer(d, t_norm, 1)


PAINTERS = {
    "title": paint_title,
    "points": paint_points,
    "quote": paint_quote,
    "wave": paint_wave,
    "image": lambda img, s, t, p: paint_image(img, s, t, p, s.get("_image_path")),
    "end": paint_end,
}


# ---------------- renderer ----------------

def render_scene(scene: dict, audio_path: Path | None, out_path: Path,
                 workdir: Path, size=(1280, 720), fps: int = FPS,
                 progress=None) -> Path:
    """Render one scene mp4 (h264 + its own audio).
    ui_* scene types delegate to the UI-demo renderer (motion_ui)."""
    global W, H
    if (scene.get("type") or "").startswith("ui_"):
        from motion_ui import render_ui_scene
        return render_ui_scene(scene, audio_path, out_path, workdir,
                               fps=fps, progress=progress)
    W, H = size
    dur = float(scene.get("duration") or 4.0)
    frames_n = max(int(dur * fps), fps)
    fdir = workdir / "frames"
    fdir.mkdir(parents=True, exist_ok=True)
    peaks = audio_peaks(audio_path, frames_n) if audio_path else []
    painter = PAINTERS.get(scene.get("type") or "title", paint_title)

    narr = scene.get("narration", "")
    from motion_ui import _caption
    for f in range(frames_n):
        img = _bg(f / frames_n)
        painter(img, scene, f / max(frames_n - 1, 1), peaks)
        if narr:
            _caption(ImageDraw.Draw(img), narr, f / max(frames_n - 1, 1) * dur, dur)
        img.save(fdir / f"f{f:05d}.png")
        if progress and f % 15 == 0:
            progress(f / frames_n)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-framerate", str(fps), "-i", str(fdir / "f%05d.png")]
    if audio_path and Path(audio_path).exists():
        cmd += ["-i", str(audio_path), "-c:a", "aac", "-b:a", "192k",
                "-shortest"]
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-c:a", "aac", "-shortest"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps), str(out_path)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=3600)
    for p in fdir.glob("*.png"):
        p.unlink()
    fdir.rmdir()
    return out_path


def concat_scenes(clips: list[Path], audio_path: Path | None,
                  out_path: Path) -> Path:
    lst = out_path.parent / "concat.txt"
    lst.write_text("".join(f"file '{c.as_posix()}'\n" for c in clips), encoding="utf-8")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
           "-i", str(lst)]
    if audio_path and Path(audio_path).exists():
        cmd += ["-i", str(audio_path), "-map", "0:v", "-map", "1:a",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest"]
    else:
        cmd += ["-c", "copy"]
    cmd += [str(out_path)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=3600)
    lst.unlink(missing_ok=True)
    return out_path
