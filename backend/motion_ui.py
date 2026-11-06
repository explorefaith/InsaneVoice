"""InsaneVoice — UI-demo scene renderer + sound effects.

Paints animated, simplified mockups of the real InsaneVoice app (brand
paper/ink/vermillion), moves a cursor, clicks buttons, types text, opens
dropdowns — with synthesised sound effects mixed under the narration.
Used by the commercial and available to Agent Studio scenes.
"""
from __future__ import annotations

import math
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import motion
from motion import (PAPER, PAPER2, INK, INK2, INK3, VERM, LINE,
                    W, H, SERIF, SERIF_I, SANS, _ease, _bg, _wrap)

PAPER3 = (228, 219, 202)

SR = 44100


# ---------------- sound effects ----------------

def _env(n, a, r):
    e = np.ones(n)
    na, nr = int(a * SR), int(r * SR)
    if na > 0:
        e[:na] = np.linspace(0, 1, na)
    if nr > 0:
        e[-nr:] *= np.linspace(1, 0, nr)
    return e


def sfx(kind: str) -> np.ndarray:
    rng = np.random.default_rng(11)
    if kind == "click":
        n = int(0.05 * SR)
        t = np.arange(n) / SR
        y = (np.sin(2 * np.pi * 1100 * t) * np.exp(-t * 90)
             + rng.standard_normal(n) * 0.25 * np.exp(-t * 220))
        return y * 0.5 * _env(n, 0.002, 0.01)
    if kind == "type":
        n = int(0.03 * SR)
        t = np.arange(n) / SR
        y = np.sin(2 * np.pi * 1800 * t) * np.exp(-t * 260)
        return y * 0.22
    if kind == "whoosh":
        n = int(0.45 * SR)
        t = np.arange(n) / SR
        noise = rng.standard_normal(n)
        cut = np.linspace(300, 3800, n)
        alpha = np.exp(-2 * np.pi * cut / SR)
        y = np.zeros(n); acc = 0.0
        for i in range(n):
            acc = (1 - alpha[i]) * noise[i] + alpha[i] * acc
            y[i] = acc
        return (y * np.sin(np.pi * t / 0.45) ** 1.4) * 0.5
    if kind == "pop":
        n = int(0.12 * SR)
        t = np.arange(n) / SR
        f = np.linspace(420, 170, n)
        y = np.sin(2 * np.pi * f * t) * np.exp(-t * 26)
        return y * 0.5
    if kind == "chime":
        n = int(0.9 * SR)
        t = np.arange(n) / SR
        y = np.zeros(n)
        for i, f in enumerate([880, 1108.7, 1318.5]):
            start = int(i * 0.09 * SR)
            tt = t[: n - start]
            y[start:] += np.sin(2 * np.pi * f * tt) * np.exp(-tt * 4.2) * 0.28
        return y
    if kind == "success":
        n = int(0.7 * SR)
        t = np.arange(n) / SR
        y = np.zeros(n)
        for i, f in enumerate([659.3, 987.8]):
            start = int(i * 0.1 * SR)
            tt = t[: n - start]
            y[start:] += np.sin(2 * np.pi * f * tt) * np.exp(-tt * 5) * 0.3
        return y
    raise ValueError(kind)


def build_sfx_track(events: list[dict], duration: float, out: Path) -> Path:
    n = int((duration + 0.2) * SR)
    track = np.zeros(n, dtype=np.float32)
    for ev in events:
        s = sfx(ev["k"])
        i0 = int(min(ev.get("t", 0), duration) * SR)
        i1 = min(n, i0 + len(s))
        if i1 > i0:
            track[i0:i1] += s[: i1 - i0].astype(np.float32)
    peak = np.max(np.abs(track)) or 1.0
    if peak > 0.9:
        track *= 0.9 / peak
    import soundfile as sf
    sf.write(str(out), track, SR)
    return out


# ---------------- drawing helpers ----------------

def _rr(d, box, r, fill=None, outline=None, width=1):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def _btn(d, box, label, pressed=False, accent=False, small=False):
    x0, y0, x1, y1 = box
    fill = (VERM if accent else INK) if not pressed else (tuple(int(c * 0.78) for c in (VERM if accent else INK)))
    _rr(d, box, 6, fill=fill)
    f = SANS(15 if small else 17, bold=True)
    tw = d.textlength(label, font=f)
    d.text(((x0 + x1) / 2 - tw / 2, (y0 + y1) / 2 - 11), label, font=f,
           fill=(PAPER if not pressed else (255, 240, 232)))


def _field(d, box, text="", focus=False, typed_frac=1.0, placeholder=""):
    x0, y0, x1, y1 = box
    _rr(d, box, 6, fill=(251, 248, 241),
        outline=(INK if focus else LINE), width=2 if focus else 1)
    shown = text[: max(0, int(len(text) * typed_frac))]
    if shown:
        d.text((x0 + 12, y0 + (y1 - y0) / 2 - 10), shown, font=SANS(15), fill=INK)
    elif placeholder:
        d.text((x0 + 12, y0 + (y1 - y0) / 2 - 10), placeholder, font=SANS(15), fill=(167, 157, 138))


FONT_DIR = Path("C:/Windows/Fonts")


def _lang_font(size, bold=False, text=""):
    """Unicode-capable font chosen by script (Bangla/CJK/Arabic/Latin)."""
    def load(name):
        try:
            return ImageFont.truetype(str(FONT_DIR / name), size)
        except Exception:
            return None
    t = text or ""
    if any("ঀ" <= ch <= "৿" for ch in t):      # Bengali/Assamese
        return load("Nirmala.ttf") or load("vrinda.ttf")
    if any("ऀ" <= ch <= "ॿ" for ch in t):      # Devanagari
        return load("Nirmala.ttf")
    if any("஀" <= ch <= "௿" for ch in t) or any(
            "ఀ" <= ch <= "౿" for ch in t) or any(
            "਀" <= ch <= "੿" for ch in t):     # Tamil/Telugu/Gurmukhi
        return load("Nirmala.ttf")
    if any("؀" <= ch <= "ۿ" for ch in t):      # Arabic
        return load("Nirmala.ttf") or load("arial.ttf")
    if any("一" <= ch <= "鿿" for ch in t):      # CJK
        return load("msyh.ttc") or load("malgun.ttf")
    if any("가" <= ch <= "힯" for ch in t):      # Hangul
        return load("malgun.ttf")
    return SANS(size, bold)


def _cursor(d, x, y, click_t=None):
    # click ripple
    if click_t is not None and 0 <= click_t <= 1:
        r = 8 + 26 * click_t
        a = 1 - click_t
        d.ellipse([x - r, y - r, x + r, y + r],
                  outline=tuple(int(VERM[i] * a + PAPER[i] * (1 - a)) for i in range(3)),
                  width=3)
    # arrow
    d.polygon([(x, y), (x, y + 22), (x + 6, y + 16), (x + 11, y + 27),
               (x + 15, y + 25), (x + 10, y + 14), (x + 17, y + 13)],
              fill=INK, outline=PAPER)


def _move(points, t):
    """points: [(x,y), ...] eased multi-leg path; t in 0..1"""
    if len(points) == 1:
        return points[0]
    seg = 1 / (len(points) - 1)
    i = min(int(t / seg), len(points) - 2)
    lt = _ease((t - i * seg) / seg)
    (x0, y0), (x1, y1) = points[i], points[i + 1]
    return (x0 + (x1 - x0) * lt, y0 + (y1 - y0) * lt)


def _app_frame(t_norm):
    """Paper bg + app window chrome + sidebar."""
    img = _bg(t_norm)
    d = ImageDraw.Draw(img)
    # window
    _rr(d, [40, 26, W - 40, H - 26], 16, fill=PAPER, outline=LINE, width=2)
    # sidebar
    _rr(d, [40, 26, 236, H - 26], 16, fill=PAPER)
    d.rectangle([40, 26, 236, H - 26], fill=(244, 239, 230))
    d.line([236, 26, 236, H - 26], fill=LINE, width=2)
    # brand
    for i, hh in enumerate([10, 20, 14, 30, 22, 34, 24, 16]):
        x = 62 + i * 8
        d.rounded_rectangle([x, 56 - hh / 2, x + 5, 56 + hh / 2], radius=2.5, fill=INK)
    _wd = d.textlength("Insane", font=SERIF_I(19))
    d.text((138, 44), "Insane", font=SERIF_I(19), fill=INK)
    d.text((138 + _wd + 1, 44), "Voice", font=SERIF_I(19), fill=VERM)
    # menu groups
    menus = [("Dashboard", True)] if False else []
    items = ["Dashboard", "Studio", "Director's Studio", "Voice DNA",
             "Voice Library", "Voice Design", "Voice Changer", "Batch Studio",
             "Voice Isolator", "Transcribe", "Dubbing Studio",
             "Agent Studio", "Connections", "History"]
    y = 96
    for i, it in enumerate(items):
        active = i in (1, 4, 12)  # depends on scene; overridden by caller param
        pass
    return img, d


def _sidebar(d, active_idx):
    items = ["Dashboard", "Studio", "Director's Studio", "Voice DNA",
             "Recorder", "Voice Library", "Voice Design", "Voice Changer",
             "Batch Studio", "Voice Isolator", "Transcribe",
             "Dubbing Studio", "Agent Studio", "Connections", "History"]
    y = 92
    for i, it in enumerate(items):
        if i == active_idx:
            _rr(d, [52, y - 7, 226, y + 15], 4, fill=INK)
            d.text((66, y - 2), it, font=SANS(13, bold=True), fill=PAPER)
        else:
            d.text((66, y - 2), it, font=SANS(13), fill=INK2)
        y += 27


# ---------------- UI scene painters ----------------

def ui_record(img, d, s, t, cursor_xy, clicks):
    _sidebar(d, 4)
    # main panel
    _rr(d, [262, 52, W - 66, H - 52], 12, fill=(251, 248, 241), outline=LINE)
    d.text((292, 78), "Recorder", font=SERIF_I(30), fill=INK)
    d.text((292, 118), "Read naturally for 10–30 seconds.", font=SANS(15), fill=INK2)
    # big record button
    bx, by = (W + 300) / 2, 300
    pulse = 1 + 0.06 * math.sin(t * 12)
    r = 40 * (pulse if s.get("_rec_on", False) else 1)
    col = PAPER if s.get("_rec_on") else VERM
    d.ellipse([bx - r, by - r, bx + r, by + r], fill=col, outline=VERM, width=3)
    if s.get("_rec_on"):
        d.rectangle([bx - 10, by - 10, bx + 10, by + 10], fill=VERM)
    else:
        d.ellipse([bx - 14, by - 14, bx + 14, by + 14], fill=PAPER)
    # waveform drawing while recording
    _rr(d, [292, 380, W - 92, 500], 8, fill=PAPER2, outline=LINE)
    if s.get("_rec_on", False):
        rng = np.random.default_rng(3)
        n = int((W - 92 - 292 - 24) / 7)
        for i in range(n):
            p = rng.uniform(0.15, 0.95) * min(1, i / (n * 0.7) * 3 if i < n * 0.3 else 1)
            h = max(3, p * 90 * (0.6 + 0.4 * math.sin(i * 0.9)))
            x = 304 + i * 7
            d.rounded_rectangle([x, 440 - h / 2, x + 4, 440 + h / 2], radius=2, fill=INK)
    # timer
    if s.get("_rec_on"):
        d.text((bx - 30, 340), f"00:{int(t * 30):02d}", font=SERIF(30), fill=INK)
    _cursor(d, cursor_xy[0], cursor_xy[1], clicks)


def ui_clone(img, d, s, t, cursor_xy, clicks):
    _sidebar(d, 5)
    _rr(d, [262, 52, W - 66, H - 52], 12, fill=(251, 248, 241), outline=LINE)
    d.text((292, 78), "Voice DNA", font=SERIF_I(30), fill=INK)
    # radar animating out
    cx, cy, R = (W + 300) / 2 - 120, 330, 110
    vals = [0.66, 1.0, 0.98, 0.0, 0.53, 0.51, 0.89, 0.43]
    labels = ["pitch", "depth", "warmth", "bright", "grit", "air", "clarity", "energy"]
    n = len(vals)
    for ring in range(1, 5):
        pts = []
        for i in range(n + 1):
            a = -math.pi / 2 + i * 2 * math.pi / n
            pts.append((cx + R * ring / 4 * math.cos(a), cy + R * ring / 4 * math.sin(a)))
        d.line(pts, fill=LINE, width=1)
    for i in range(n):
        a = -math.pi / 2 + i * 2 * math.pi / n
        d.line([cx, cy, cx + R * math.cos(a), cy + R * math.sin(a)], fill=LINE)
    grow = _ease(min(1, t * 1.8))
    pts = []
    for i, v in enumerate(vals):
        a = -math.pi / 2 + i * 2 * math.pi / n
        pts.append((cx + R * max(0.06, v * grow) * math.cos(a),
                    cy + R * max(0.06, v * grow) * math.sin(a)))
    d.polygon(pts, fill=(201, 67, 43, 40), outline=None)
    d.line(pts + [pts[0]], fill=VERM, width=3)
    for x, y in pts:
        d.ellipse([x - 4, y - 4, x + 4, y + 4], fill=VERM)
    for i, lab in enumerate(labels):
        a = -math.pi / 2 + i * 2 * math.pi / n
        d.text((cx + (R + 16) * math.cos(a), cy + (R + 16) * math.sin(a)),
               lab, font=SANS(13), fill=INK2, anchor="mm")
    # archetype pill pops
    if t > 0.45:
        a = _ease((t - 0.45) / 0.25)
        tw = 250 * a
        _rr(d, [cx - tw / 2, cy + R + 34, cx + tw / 2, cy + R + 70], 99,
            fill=PAPER, outline=INK)
        if a > 0.9:
            d.text((cx, cy + R + 41), "Smooth Dark Mezzo-Soprano", font=SERIF(18),
                   fill=INK, anchor="ma")
    # voice card right
    _rr(d, [900, 120, W - 100, 320], 12, fill=PAPER, outline=LINE)
    d.text((924, 140), "Demo British", font=SERIF_I(22), fill=INK)
    for i, (lab, v) in enumerate([("pitch", 66), ("warmth", 98), ("brightness", 5), ("grit", 53)]):
        y = 190 + i * 30
        d.text((924, y), lab, font=SANS(13), fill=INK2)
        d.rounded_rectangle([1020, y + 4, 1140, y + 10], 3, fill=PAPER3)
        d.rounded_rectangle([1020, y + 4, 1020 + int(120 * v / 100 * _ease(min(1, t * 2))), y + 10],
                            3, fill=VERM if lab == "pitch" else INK2)
    if t > 0.6:
        _btn(d, [924, 340, 1080, 380], "＋ Save as voice", accent=True)
    _cursor(d, cursor_xy[0], cursor_xy[1], clicks)


def ui_generate(img, d, s, t, cursor_xy, clicks):
    _sidebar(d, 1)
    _rr(d, [262, 52, W - 66, H - 52], 12, fill=(251, 248, 241), outline=LINE)
    d.text((292, 78), "Studio", font=SERIF_I(30), fill=INK)
    _field(d, [292, 130, 820, 250],
           "Welcome back to the channel. [sigh] Today was long. But [happy]this news is amazing[/happy]!",
           typed_frac=min(1, t * 2.2))
    # emotion chips
    x = 292
    for chip in ["[pause]", "[sigh]", "[gasp]", "happy span", "whisper"]:
        tw = d.textlength(chip, font=SANS(13)) + 18
        _rr(d, [x, 262, x + tw, 290], 99, fill=PAPER2, outline=LINE)
        d.text((x + 9, 267), chip, font=SANS(13), fill=INK2)
        x += tw + 8
    # generate button (pressed after click)
    pressed = s.get("_pressed", False)
    _btn(d, [292, 310, 500, 356], "✦ Generate speech", pressed=pressed, accent=True)
    # progress + result
    if t > 0.42:
        p = min(1, (t - 0.42) / 0.3)
        d.rounded_rectangle([292, 372, 820, 382], 5, fill=PAPER3)
        d.rounded_rectangle([292, 372, 292 + int(528 * p), 382], 5, fill=VERM)
        d.text((292, 390), f"Generating… {int(p * 100)}%", font=SANS(13), fill=INK2)
    if t > 0.78:
        _rr(d, [292, 420, 820, 560], 10, fill=PAPER, outline=LINE)
        rng = np.random.default_rng(9)
        for i in range(60):
            p = rng.uniform(0.2, 1) * _ease((t - 0.78) / 0.2)
            h = max(3, p * 70)
            x = 312 + i * 8.2
            d.rounded_rectangle([x, 490 - h / 2, x + 5, 490 + h / 2], radius=2.5, fill=INK)
        d.text((312, 432), "▶", font=SANS(20), fill=VERM)
        d.text((340, 434), "Your voice — generated locally, free.", font=SANS(14), fill=INK2)
    _cursor(d, cursor_xy[0], cursor_xy[1], clicks)


def ui_language(img, d, s, t, cursor_xy, clicks):
    _sidebar(d, 1)
    _rr(d, [262, 52, W - 66, H - 52], 12, fill=(251, 248, 241), outline=LINE)
    d.text((292, 78), "Studio — pick your language", font=SERIF_I(30), fill=INK)
    langs_list = [("English", False), ("Español", False), ("Français", False),
                  ("中文", False), ("日本語", False), ("한국어", False),
                  ("বাংলা (Bangla)", True), ("हिन्दी", True), ("العربية", True),
                  ("Deutsch", True), ("Português", True), ("Русский", True),
                  ("Italiano", True), ("Türkçe", True), ("Tiếng Việt", True)]
    # closed select
    _field(d, [292, 130, 640, 172], "English", focus=t > 0.18)
    # dropdown opens
    if t > 0.18:
        drop = _ease(min(1, (t - 0.18) / 0.25))
        hh = int(min(len(langs_list), 10) * 38 * drop)
        _rr(d, [292, 176, 640, 176 + hh], 8, fill=(251, 248, 241), outline=INK)
        d.save() if False else None
        # clip via rectangle drawing only within panel
        for i, (lab, mms) in enumerate(langs_list):
            y = 176 + i * 38
            if y + 34 > 176 + hh:
                break
            hl = 0.18 <= t and abs(i - s.get("_sel_idx", -1)) < 0.5 and t > 0.25 + i * 0.02
            if i == s.get("_sel_idx", -1) and t > s.get("_sel_t", 9):
                _rr(d, [296, y + 3, 636, y + 34], 4, fill=(246, 227, 222))
                d.text((312, y + 9), lab, font=_lang_font(16, bold=True, text=lab), fill=VERM)
                d.text((600, y + 9), "✓", font=SANS(16, bold=True), fill=VERM)
            else:
                d.text((312, y + 9), lab, font=_lang_font(16, text=lab),
                       fill=INK if not mms else INK2)
            if mms:
                _rr(d, [560, y + 9, 600, y + 28], 9, fill=PAPER2)
                d.text((566, y + 10), "new", font=SANS(11), fill=INK3)
    d.text((680, 130), "32 languages · Bangla, Hindi, Arabic…", font=SANS(15), fill=INK2)
    d.text((680, 160), "powered by MeloTTS + Meta MMS — all offline", font=SANS(13), fill=INK3)
    _cursor(d, cursor_xy[0], cursor_xy[1], clicks)


def ui_connections(img, d, s, t, cursor_xy, clicks):
    _sidebar(d, 13)
    _rr(d, [262, 52, W - 66, H - 52], 12, fill=(251, 248, 241), outline=LINE)
    d.text((292, 78), "Connections", font=SERIF_I(30), fill=INK)
    d.text((292, 116), "Bring your own model endpoints — keys stay on this machine.",
           font=SANS(14), fill=INK2)
    # text provider card
    _rr(d, [292, 150, 900, 420], 12, fill=PAPER, outline=LINE)
    d.text((316, 168), "Text model — script writing", font=SERIF_I(20), fill=INK)
    _field(d, [316, 210, 876, 250], "https://api.openai.com/v1")
    _field(d, [316, 262, 876, 302], "•" * 18, focus=0.3 < t < 0.62,
           typed_frac=min(1, max(0, (t - 0.3) / 0.3) * 18) / 18 if t > 0.3 else 0)
    if t > 0.62:
        _rr(d, [740, 168, 876, 196], 99, fill=(226, 235, 226), outline=(62, 107, 79))
        d.text((752, 173), "key saved ✓", font=SANS(13, bold=True), fill=(62, 107, 79))
    # model chips appearing
    chips = ["gpt-4o-mini", "deepseek-chat", "glm-4-flash"]
    x = 316
    for i, ch in enumerate(chips):
        if t > 0.68 + i * 0.07:
            a = _ease((t - 0.68 - i * 0.07) / 0.2)
            tw = (d.textlength(ch, font=SANS(13)) + 34) * a
            _rr(d, [x, 318, x + tw, 348], 99, fill=INK)
            d.text((x + 10, 324), ch, font=SANS(13), fill=PAPER)
            d.ellipse([x + tw - 20, 325, x + tw - 8, 337], fill=(244, 239, 230, 46))
            x += tw + 10
    if t > 0.9:
        d.text((316, 366), "failover: if one model fails → the next one continues with the same context",
               font=SANS(13), fill=INK3)
    _cursor(d, cursor_xy[0], cursor_xy[1], clicks)


def ui_agent(img, d, s, t, cursor_xy, clicks):
    _sidebar(d, 12)
    _rr(d, [262, 52, W - 66, H - 52], 12, fill=(251, 248, 241), outline=LINE)
    d.text((292, 78), "Agent Studio", font=SERIF_I(30), fill=INK)
    _field(d, [292, 124, 820, 196],
           "Make a 60-second video about owning your voice.",
           typed_frac=min(1, t * 2))
    pressed = t > 0.3
    _btn(d, [292, 210, 480, 250], "✦ Start agent run", pressed=pressed, accent=True)
    stages = ["script", "audio", "visuals", "render"]
    y = 280
    for i, st in enumerate(stages):
        done = t > 0.42 + i * 0.12
        running = (t > 0.30 + i * 0.12) and not done
        col = (62, 107, 79) if done else (VERM if running else INK3)
        d.ellipse([292, y, 312, y + 20], outline=col, width=2,
                  fill=(226, 235, 226) if done else PAPER)
        if done:
            d.line([297, y + 10, 302, y + 15], fill=col, width=2)
            d.line([302, y + 15, 310, y + 5], fill=col, width=2)
        if running:
            a = (math.sin(t * 40) + 1) / 2
            d.ellipse([298 + 4 * a, y + 6, 306 + 4 * a, y + 14], fill=col)
        d.text((326, y + 1), {"script": "Script written by your model",
                              "audio": "Voiced with your cloned voice",
                              "visuals": "Motion engine renders scenes",
                              "render": "ffmpeg stitches the MP4"}[st],
               font=SANS(15), fill=INK if (done or running) else INK3)
        y += 34
    if t > 0.9:
        p = _ease((t - 0.9) / 0.1)
        d.rounded_rectangle([292, 430, 820, 442], 6, fill=PAPER3)
        d.rounded_rectangle([292, 430, 292 + int(528 * p), 442], 6, fill=VERM)
    # video thumbnail
    if t > 0.95:
        _rr(d, [860, 120, W - 90, 360], 10, fill=INK)
        d.polygon([(1050, 220), (1050, 268), (1092, 244)], fill=PAPER)
        d.text((900, 380), "InsaneVoice_Agent_Video.mp4", font=SANS(14), fill=INK2)
    _cursor(d, cursor_xy[0], cursor_xy[1], clicks)


def ui_voices(img, d, s, t, cursor_xy, clicks):
    _sidebar(d, 5)
    _rr(d, [262, 52, W - 66, H - 52], 12, fill=(251, 248, 241), outline=LINE)
    d.text((292, 78), "Voice Library", font=SERIF_I(30), fill=INK)
    d.text((292, 118), "70+ preset voices · filter by language", font=SANS(15), fill=INK2)
    cards = [("বাংলা", "Bangla · Deep", "বাং"), ("English", "Warm Baritone", "E"),
             ("हिन्दी", "Hindi · Natural", "ह"), ("日本語", "Bright Alto", "J"),
             ("Deutsch", "Slow Cinematic", "D"), ("中文", "Soprano Clear", "C"),
             ("Español", "Soft Airy", "S"), ("Français", "Fast Energetic", "F"),
             ("العربية", "Deep Narrator", "A")]
    for i, (lang, name, initial) in enumerate(cards):
        col = i % 3
        row = i // 3
        a = _ease(max(0, (t - 0.15 - i * 0.05)) / 0.3)
        if a <= 0:
            continue
        x0 = 292 + col * 322
        y0 = 156 + row * 118 + (1 - a) * 16
        _rr(d, [x0, y0, x0 + 306, y0 + 104], 10, fill=PAPER, outline=LINE)
        d.rectangle([x0 + 14, y0 + 14, x0 + 50, y0 + 50], fill=INK)
        d.text((x0 + 32, y0 + 32), initial, font=SERIF_I(20), fill=PAPER, anchor="mm")
        d.text((x0 + 62, y0 + 16), name, font=SERIF_I(17), fill=INK)
        d.text((x0 + 62, y0 + 42), lang, font=SANS(12), fill=INK3)
        bw = int(180 * a)
        d.rounded_rectangle([x0 + 62, y0 + 66, x0 + 242, y0 + 72], 3, fill=PAPER3)
        d.rounded_rectangle([x0 + 62, y0 + 66, x0 + 62 + bw, y0 + 72], 3,
                            fill=VERM if i % 3 == 0 else INK2)
    _cursor(d, cursor_xy[0], cursor_xy[1], clicks)


UI_PAINTERS = {
    "ui_record": ui_record,
    "ui_clone": ui_clone,
    "ui_generate": ui_generate,
    "ui_language": ui_language,
    "ui_connections": ui_connections,
    "ui_agent": ui_agent,
    "ui_voices": ui_voices,
}


# ---------------- renderer ----------------

def render_ui_scene(scene: dict, audio_path: Path, out_path: Path,
                    workdir: Path, fps: int = 30, progress=None) -> Path:
    painter = UI_PAINTERS[scene["type"]]
    dur = float(scene.get("duration") or 5)
    frames_n = max(int(dur * fps), fps)
    fdir = workdir / "frames"
    fdir.mkdir(parents=True, exist_ok=True)

    rec_on = scene["type"] == "ui_record"
    for f in range(frames_n):
        tn = f / max(frames_n - 1, 1)
        img, d = _app_frame(tn)
        s = dict(scene)
        s["_rec_on"] = rec_on and 0.25 < tn < 0.8
        s["_pressed"] = 0.3 < tn < 0.38 or (scene["type"] == "ui_agent" and tn > 0.3)
        s["_sel_idx"] = scene.get("sel_idx", 6)
        s["_sel_t"] = scene.get("sel_t", 0.6)
        cur = _move(scene.get("path", [(900, 620), (400, 330)]), min(1, tn * 1.15))
        click_local = None
        for ct in scene.get("clicks", []):
            lt = tn - ct
            if 0 <= lt <= 0.12:
                click_local = lt / 0.12
        painter(img, d, s, tn, cur, click_local)
        img.save(fdir / f"f{f:05d}.png")
        if progress and f % 20 == 0:
            progress(f / frames_n)

    # audio: narration + sfx overlay
    mixed = workdir / "mix.wav"
    sfx_wav = None
    if scene.get("sfx"):
        sfx_wav = build_sfx_track(scene["sfx"], dur, workdir / "sfx.wav")
    if audio_path and Path(audio_path).exists() and sfx_wav:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                        "-i", str(audio_path), "-i", str(sfx_wav),
                        "-filter_complex",
                        "[0:a]aresample=44100[n];[1:a]volume=0.9[s];"
                        "[n][s]amix=inputs=2:duration=first:normalize=0",
                        str(mixed)], check=True, capture_output=True)
        sfx_wav.unlink(missing_ok=True)
    elif sfx_wav:
        mixed = sfx_wav
    else:
        mixed = audio_path

    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-framerate", str(fps), "-i", str(fdir / "f%05d.png")]
    if mixed and Path(mixed).exists():
        cmd += ["-i", str(mixed), "-c:a", "aac", "-b:a", "192k", "-shortest"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps), str(out_path)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=3600)
    for p in fdir.glob("*.png"):
        p.unlink()
    fdir.rmdir()
    return out_path
