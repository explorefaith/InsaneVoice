"""Cartoon motion engine — LLM-written HTML scenes rendered frame-by-frame.

Each scene becomes a self-contained HTML/CSS/SVG animation with a strict
contract: the page must define `window.render(tSeconds)` that deterministically
positions every element for time t. A headless Chrome (system binary via
Playwright) screenshots the page at 12 fps (classic cartoon frame rate) and
ffmpeg turns frames + narration into the final clip.

If a scene's HTML fails validation twice, the caller falls back to the
static-image pipeline for that scene.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
from pathlib import Path

CHROME = "/usr/bin/google-chrome"
FPS = 12
WIDTH, HEIGHT = 1920, 1080

PROMPT_TEMPLATE = """You are an animation director. Write ONE self-contained HTML file that renders a single 2D cartoon scene as a programmatic animation.

Cartoon scene. Duration: {duration:.1f} seconds.
Scene description: {visual}
Character (keep consistent): {character}

STRICT TECHNICAL CONTRACT (violations fail automatically):
1. One file: <!doctype html> ... </html>. All CSS/JS inline. NO external resources, no fonts, no images, no network.
2. A fixed stage exactly {width}x{height} px (body margin 0, stage div absolute, overflow hidden).
3. MUST define: window.render = function(t) {{ ... }} — t is seconds since scene start (0..{duration:.1f}). It must deterministically set positions/rotations/opacity/scale of every animated element for that instant (pure interpolation, no randomness, no setInterval, no CSS animations/transitions).
4. Before first render, page must already look complete at t=0 without render() being called (initial CSS state = frame 0), so even a static screenshot is a valid cartoon frame.
5. Flat 2D vector-cartoon look: inline SVG shapes (circles, ellipses, paths), soft warm night palette, clean silhouettes. NO text, NO letters, NO speech bubbles anywhere.
6. Real motion (this is a motion cartoon, not a still): the character visibly acts out the scene — e.g. shifts/bobs, blinks (eyes scale-y), arm/antenna moves, props drift; use smooth eased interpolation like t01 = Math.min(1, Math.max(0, (t - a) / (b - a))) and e = t01*t01*(3-2*t01). At least 4 distinct movement moments across the duration. Gentle motion, no strobe/flash.
7. Everything must stay inside the stage; nothing important cut off.
8. Keep it compact — under 250 lines. Simple, readable code beats elaborate code.

Return ONLY the HTML file content (no explanations, no markdown fences)."""

MAX_TOKENS = 8000


def _extract_html(txt: str) -> str:
    lo = txt.lower()
    start = lo.find("<!doctype")
    if start < 0:
        start = lo.find("<html")
    if start < 0:
        raise ValueError("no html document in response")
    end = lo.rfind("</html>")
    body = txt[start: end + 7] if end >= 0 else txt[start:]
    if end < 0:
        body += "\n</body></html>"      # tolerate truncated output
    return body


class MotionRenderer:
    """One headless Chrome per job; pages reused per scene."""

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            executable_path=CHROME, headless=True,
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

    # ---------- validation ----------

    def validate(self, html_path: Path, duration: float) -> None:
        page = self._page
        page.goto(html_path.as_uri(), wait_until="load", timeout=15000)
        has_render = page.evaluate("typeof window.render === 'function'")
        if not has_render:
            raise ValueError("page does not define window.render(t)")
        shots = []
        for t in (0.0, duration * 0.5, duration * 0.92):
            page.evaluate(f"window.render({t!r})")
            shots.append(page.screenshot())
        _require_real_picture(shots)

    # ---------- frame capture ----------

    def capture(self, html_path: Path, duration: float, out_dir: Path,
                progress=None) -> int:
        page = self._page
        page.goto(html_path.as_uri(), wait_until="load", timeout=15000)
        n = max(2, round(duration * FPS))
        out_dir.mkdir(parents=True, exist_ok=True)
        for f in range(n):
            t = f / FPS
            page.evaluate(f"window.render({t!r})")
            page.screenshot(path=str(out_dir / f"f{f:05d}.png"), type="png")
            if progress and f % max(1, n // 8) == 0:
                progress(f, n)
        # sanity: first and last frame must be real pictures
        blobs = [(out_dir / "f00000.png").read_bytes()]
        last = out_dir / f"f{n-1:05d}.png"
        if last.exists():
            blobs.append(last.read_bytes())
        _require_real_picture(blobs)
        return n


def request_scene_html(text_cfg: dict, scene: dict, duration: float,
                       character: str) -> str:
    """LLM-only step (no browser) — safe to run in parallel threads.
    Tries each model in text_cfg["models"] order once."""
    prompt = PROMPT_TEMPLATE.format(duration=duration, visual=scene["visual"],
                                    character=character, width=WIDTH, height=HEIGHT)
    last_err = None
    for model in text_cfg["models"]:
        try:
            from cartoon import _post_json          # reuse http helper
            r = _post_json(f"{text_cfg['base_url']}/chat/completions",
                           text_cfg["api_key"], {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.4, "max_tokens": MAX_TOKENS}, timeout=300)
            return _extract_html(r["choices"][0]["message"]["content"])
        except urllib.error.HTTPError as e:
            last_err = f"{model}: HTTP {e.code}"
            print(f"[motion] html request failed: {last_err}", flush=True)
            time.sleep(4)
        except Exception as e:                       # noqa: BLE001
            last_err = f"{model}: {type(e).__name__}: {e}"
            print(f"[motion] html request failed: {last_err}", flush=True)
            time.sleep(4)
    raise RuntimeError(f"scene html failed on all models: {last_err}")


def _require_real_picture(png_blobs) -> None:
    """Reject blank/solid frames (broken HTML renders as near-uniform pixels)."""
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
