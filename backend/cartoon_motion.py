"""Cartoon motion engine — rigged-character scenes rendered frame-by-frame.

Instead of asking the LLM to draw (error-prone), the LLM writes a compact
CHOREOGRAPHY JSON: pick ready-made characters/props from the rig library
(humans, animals, trees, rivers, houses, weather...), place them, and time
their gestures. `backend/assets/cartoon_rig.js` does all drawing/animation
deterministically — real walk cycles, extreme gestures, and automatic
lip-sync during the narration window. Headless Chrome captures 15fps frames.

Fallback per scene: Recraft image (storybook-style) if choreography fails.
"""
from __future__ import annotations

import json
import time
import urllib.error
from pathlib import Path

RIG_JS_PATH = Path(__file__).resolve().parent / "assets" / "cartoon_rig.js"
FPS = 15
WIDTH, HEIGHT = 1920, 1080

ACTORS = ["man", "woman", "boy", "girl", "oldman", "cat", "dog", "bird"]
PROPS = ["tree", "pine", "bush", "flower", "river", "pond", "house", "fence", "bench", "rock",
         "table", "chair", "bookshelf", "sun", "moon", "clouds", "stars", "rain", "snow",
         "fireflies", "mountains", "hills", "road", "butterfly", "bee", "fish"]
GROUNDS = ["grass", "sand", "wood", "floor", "stone", "snow"]
TIMES = ["day", "sunset", "night"]
GESTURES = ["wave", "point", "cheer", "think", "carry", "nod", "shake", "bow", "dance", "spin", "jump", "sit"]
EMOTES = ["happy", "sad", "surprised", "angry", "neutral"]

CATALOG = f"""ACTORS (rigged, they walk/gesture/lip-sync automatically):
  man, woman, boy, girl, oldman, cat, dog, bird
  human params: skin ("#f6c99f" fair | "#e0ac69" tan | "#a9714b" brown | "#6b4429" dark),
    hair "#hex", hairstyle ("short"|"long"|"bun"|"curly"|"bald"), shirt "#hex", pants "#hex",
    glasses true/false, hat true/false. oldman = elderly. boy/girl render as children.
PROPS (place 3-6 for a rich scene): tree, pine, bush, flower, river, pond, house, fence,
  bench, rock, table, chair, bookshelf, sun, moon, clouds, stars, rain, snow, fireflies,
  mountains, hills, road, butterfly (flies on its own), bee (flies), fish (swims)
GROUND: grass | sand | wood | floor | stone | snow
TIME: day | sunset | night
ACTOR ACTIONS (t = [startSec, endSec] within [0, duration]):
  {{"do":"walk","to":<x>,"t":[a,b]}}          — walks across, legs animate, auto-faces
  {{"do":"gesture","name":"...","t":[a,b]}}   — wave, point, cheer, think, carry, nod, shake, bow, dance, spin, sit
  {{"do":"jump","t":[a,b]}}                    — big leap with squash & stretch
  {{"do":"face","dir":-1,"t":[a,a]}}           — turn around at that moment
  {{"do":"emote","name":"happy|sad|surprised|angry","t":[a,a]}}"""


def _rig_js() -> str:
    return RIG_JS_PATH.read_text()


def request_choreo(text_cfg: dict, scene: dict, duration: float, character: str,
                   speak=None, mood: str = "cozy") -> dict:
    """LLM step (no browser) — returns validated choreography dict."""
    sp = (f'The main character SPEAKS from t={speak[0]:.1f} to t={speak[1]:.1f} — set '
          f'"speaker": true on that actor and give it talking gestures in that window.')
    prompt = f"""You are a cartoon animation director. Output STRICT JSON only (no markdown, no comments) describing ONE scene of an animated 2.5D cartoon.

Duration: {duration:.1f} seconds. Mood: {mood}.
Story beat to show: {scene['visual']}
Main character: {character} — choose the ACTOR type + params that match it best, keep it consistent.
{sp}

CATALOG
{CATALOG}

RULES
- Output shape: {{"time": "...", "ground": "...", "camera": {{"start": {{"x":0,"y":0,"zoom":1.0}}, "end": {{"x":80,"y":-30,"zoom":1.12}}}}, "props": [...], "actors": [...]}}
- "props": 3-6 entries, each {{"type":"...","x":0-1900,"y":groundY-ish,"scale":0.5-1.6}} (y optional, default ground). Sun/moon/stars/clouds high on screen (y 100-260). river spans screen (x 0, y near groundY).
- "actors": 1-3 entries, each {{"type":"...","params":{{...}},"x":200-1700,"scale":0.8-1.1,"flip":false,"speaker":true/false,"emote":"happy","actions":[...]}}
- 3-5 actions per actor covering the WHOLE duration; big theatrical energy: cross the screen, wave, jump, dance, react. The speaker gestures actively during its speech window.
- camera: slow push-in or pan (zoom 1.0 -> 1.1-1.15).
- All t values are seconds within [0, {duration:.1f}]. JSON only."""
    last_err = None
    for model in text_cfg["models"]:
        try:
            from cartoon import _post_json
            r = _post_json(f"{text_cfg['base_url']}/chat/completions",
                           text_cfg["api_key"], {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.6, "max_tokens": 3500}, timeout=240)
            txt = r["choices"][0]["message"]["content"].strip()
            txt = txt.split("```json")[-1].split("```")[0].strip()
            data = json.loads(txt[txt.index("{"): txt.rindex("}") + 1])
            return _validate_choreo(data, duration)
        except urllib.error.HTTPError as e:
            last_err = f"{model}: HTTP {e.code}"
            print(f"[motion] choreo request failed: {last_err}", flush=True)
            time.sleep(4)
        except Exception as e:      # noqa: BLE001
            last_err = f"{model}: {type(e).__name__}: {e}"
            print(f"[motion] choreo request failed: {last_err}", flush=True)
            time.sleep(4)
    raise RuntimeError(f"choreography failed on all models: {last_err}")


def _validate_choreo(data: dict, duration: float) -> dict:
    if not isinstance(data.get("actors"), list) or not data["actors"]:
        raise ValueError("no actors in choreography")
    data["time"] = data.get("time") if data.get("time") in TIMES else "day"
    data["ground"] = data.get("ground") if data.get("ground") in GROUNDS else "grass"
    if not isinstance(data.get("groundY"), (int, float)) or not (500 <= data["groundY"] <= 1000):
        data["groundY"] = 920
    data["camera"] = data.get("camera") if isinstance(data.get("camera"), dict) else \
        {"start": {"x": 0, "y": 0, "zoom": 1.0}, "end": {"x": 70, "y": -25, "zoom": 1.1}}
    props = []
    for p in (data.get("props") or [])[:8]:
        if isinstance(p, dict) and p.get("type") in PROPS:
            p["x"] = max(-100, min(2000, p.get("x", 300)))
            if isinstance(p.get("y"), (int, float)):
                p["y"] = max(60, min(980, p["y"]))
            p["scale"] = max(0.25, min(2.2, p.get("scale", 1) or 1))
            props.append(p)
    data["props"] = props
    actors = []
    for a in (data.get("actors") or [])[:3]:
        if not isinstance(a, dict) or a.get("type") not in ACTORS:
            continue
        acts = []
        for act in (a.get("actions") or [])[:7]:
            if not isinstance(act, dict) or not isinstance(act.get("t"), list) or len(act["t"]) < 2:
                continue
            t0, t1 = sorted([max(0.0, float(act["t"][0])), min(duration, float(act["t"][1]))])
            if t1 - t0 < 0.15:
                continue
            if act.get("do") == "gesture" and act.get("name") not in GESTURES:
                act["name"] = "wave"
            if act.get("do") == "emote" and act.get("name") not in EMOTES:
                act["name"] = "happy"
            act["t"] = [t0, t1]
            if act.get("do") in ("walk", "gesture", "jump", "face", "emote", "sit"):
                acts.append(act)
        a["actions"] = acts
        a["x"] = max(120, min(1800, a.get("x", 400) or 400))
        a["scale"] = max(0.35, min(1.3, a.get("scale", 1) or 1))
        actors.append(a)
    if not actors:
        raise ValueError("no valid actors after validation")
    data["actors"] = actors
    return data


def assemble_scene_html(choreo: dict, duration: float, speak_from: float,
                        speak_to: float, out_html: Path) -> Path:
    payload = json.dumps(choreo, ensure_ascii=False)
    if "</script" in payload.lower():
        payload = payload.replace("</script", "<\\/script")
    html = f"""<!doctype html><html><head><meta charset="utf-8">
<style>html,body{{margin:0;padding:0;width:{WIDTH}px;height:{HEIGHT}px;overflow:hidden;background:#0e1440}}#stage{{position:absolute;inset:0}}</style>
</head><body><div id="stage"></div>
<script>{_rig_js()}</script>
<script>
window.__SCENE = {payload};
window.IVScene.build(window.__SCENE, {duration}, {speak_from}, {speak_to});
</script></body></html>"""
    out_html.write_text(html)
    return out_html


class MotionRenderer:
    """One headless Chrome per job; page reused per scene."""

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            executable_path="/usr/bin/google-chrome", headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--force-color-profile=srgb"])
        self._page = self._browser.new_page(
            viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1)
        return self

    def __exit__(self, *exc):
        try:
            self._browser.close()
        except Exception:
            pass
        try:
            self._pw.stop()
        except Exception:
            pass
        return False

    def validate(self, html_path: Path, duration: float) -> None:
        page = self._page
        page.goto(html_path.as_uri(), wait_until="load", timeout=15000)
        ok = page.evaluate("typeof window.IVScene === 'object' && typeof window.IVScene.render === 'function'")
        if not ok:
            raise ValueError("rig/scene driver failed to load")
        shots = []
        for t in (0.0, duration * 0.5, duration * 0.9):
            page.evaluate(f"window.IVScene.render({t!r})")
            shots.append(page.screenshot())
        _require_real_picture(shots)

    def capture(self, html_path: Path, duration: float, out_dir: Path) -> int:
        page = self._page
        page.goto(html_path.as_uri(), wait_until="load", timeout=15000)
        n = max(2, round(duration * FPS))
        out_dir.mkdir(parents=True, exist_ok=True)
        for f in range(n):
            page.evaluate(f"window.IVScene.render({f / FPS!r})")
            page.screenshot(path=str(out_dir / f"f{f:05d}.png"), type="png")
        blobs = [(out_dir / "f00000.png").read_bytes()]
        last = out_dir / f"f{n-1:05d}.png"
        if last.exists():
            blobs.append(last.read_bytes())
        _require_real_picture(blobs)
        return n


def _require_real_picture(png_blobs) -> None:
    """Reject blank/solid frames (a broken scene renders as near-uniform pixels)."""
    import io
    import numpy as np
    from PIL import Image
    worst = None
    for blob in png_blobs:
        if not blob:
            continue
        arr = np.asarray(Image.open(io.BytesIO(blob)).convert("L"))
        std = float(arr.std())
        if worst is None or std < worst:
            worst = std
    if worst is not None and worst < 6.0:
        raise ValueError(f"rendered frames look blank (std={worst:.1f})")
