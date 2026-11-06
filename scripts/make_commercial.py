"""InsaneVoice commercial v2 — UI-demo scenes with sound effects.

Structure (research-backed 60-90s demo):
  Hook -> Problem -> Solution (animated app demos: record, clone, generate,
  language, voices, connections, agent) -> Proof -> CTA.
Narration: cloned preset voices, including a real Bangla line.
"""
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

import config  # noqa: E402

config.ensure_dirs()
WORK = REPO / "docs" / "_commercial_work"
WORK.mkdir(parents=True, exist_ok=True)
OUT = config.OUTPUT_DIR / "InsaneVoice_Commercial.mp4"


def pick_voice(pred):
    import storage
    for v in storage.list_voices():
        if pred(v):
            return v
    return None


SCENES = [
    dict(type="title", text="Still paying to sound like yourself?",
         sub="InsaneVoice — a free, local voice studio",
         narration="Every month, creators pay subscriptions just to sound like themselves."),
    dict(type="points", text="The problem",
         points=["Rented voices, monthly bills", "Monotone robots, no emotion",
                 "Your audio lives on someone else's cloud"],
         narration="Robotic voices. Rental voices. And your audio lives on someone else's cloud."),
    dict(type="ui_record",
         path=[(900, 620), (735, 300), (735, 300)], clicks=[0.25, 0.8],
         sfx=[{"t": 0.25, "k": "click"}, {"t": 0.3, "k": "whoosh"},
              {"t": 0.8, "k": "click"}],
         narration="InsaneVoice runs entirely on your own laptop. Record yourself for ten seconds."),
    dict(type="ui_clone",
         path=[(900, 620), (700, 380)], clicks=[0.15],
         sfx=[{"t": 0.15, "k": "click"}, {"t": 0.55, "k": "chime"}],
         narration="Voice DNA reads your fingerprint, and the cloner paints every word with your tone."),
    dict(type="ui_generate",
         path=[(900, 620), (400, 200), (396, 333)], clicks=[0.38],
         sfx=[{"t": 0.1, "k": "type"}, {"t": 0.18, "k": "type"}, {"t": 0.26, "k": "type"},
              {"t": 0.38, "k": "click"}, {"t": 0.85, "k": "success"}],
         narration="Type anything. Add sighs, gasps, whispers, happiness, then press generate."),
    dict(type="ui_language", sel_idx=6, sel_t=0.62,
         path=[(900, 620), (450, 320), (450, 398)], clicks=[0.2, 0.62],
         sfx=[{"t": 0.2, "k": "click"}, {"t": 0.45, "k": "whoosh"},
              {"t": 0.62, "k": "click"}, {"t": 0.7, "k": "pop"}],
         narration="সত্যিই! বাংলা, হিন্দি, আরবি — সব কিছু অফলাইনে কাজ করে।",
         narration_en="And yes — Bangla, Hindi, Arabic, and more. All fully offline."),
    dict(type="ui_voices",
         path=[(900, 620), (450, 300)], clicks=[],
         sfx=[{"t": 0.2, "k": "whoosh"}, {"t": 0.8, "k": "chime"}],
         narration="Seventy plus ready voices across eighteen languages, every one shaped from real D S P."),
    dict(type="ui_connections",
         path=[(900, 620), (500, 280), (500, 280)], clicks=[0.32],
         sfx=[{"t": 0.32, "k": "click"}, {"t": 0.55, "k": "type"},
              {"t": 0.66, "k": "success"}],
         narration="Bring your own model. Paste an endpoint, drop an A P I key, add fallbacks."),
    dict(type="ui_agent",
         path=[(900, 620), (390, 230)], clicks=[0.3],
         sfx=[{"t": 0.3, "k": "click"}, {"t": 0.9, "k": "chime"}],
         narration="Then the Agent Studio writes, voices and renders a full video from one prompt."),
    dict(type="points", text="Proof, not promises",
         points=["No cloud. No API keys. No bills.",
                 "Consent gate + inaudible watermark on every clip",
                 "Open source under MIT"],
         narration="Free, private, and open source. Consent gated, watermarked, and fully yours."),
    dict(type="end", text="InsaneVoice",
         narration="InsaneVoice. Your voice. Yours."),
]


def main():
    import soundfile as sf
    import numpy as np
    import engine
    import motion
    import shutil

    print("[commercial2] warming engine...", flush=True)
    engine.ensure_loaded(block=True)

    host = pick_voice(lambda v: "Warm Baritone" in v.get("name", ""))
    host = host or pick_voice(lambda v: v.get("language") == "en" and v.get("preset"))
    bangla = pick_voice(lambda v: v.get("language") == "bn")
    print(f"[commercial2] host={host['name'] if host else None} "
          f"bangla={bangla['name'] if bangla else None}", flush=True)

    clips, audios = [], []
    for i, sc in enumerate(SCENES):
        use_bangla = "বাংলা" in sc.get("narration", "")
        if use_bangla and bangla:
            voice, lang, text = bangla, "bn", sc["narration"]
        else:
            voice, lang = host, "en"
            text = sc["narration"] if not use_bangla else sc.get("narration_en", sc["narration"])
        wav = WORK / f"n{i}.wav"
        print(f"[commercial2] scene {i + 1}/{len(SCENES)} [{sc['type']}] voicing "
              f"({lang})...", flush=True)
        engine.generate(text, voice["se_path"], wav,
                        speed=1.02, tau=0.3, lang=lang)
        dur = sf.info(str(wav)).duration
        scene = {k: v for k, v in sc.items() if k != "narration"}
        scene["duration"] = round(dur + 0.55, 2)
        audios.append(wav)
        clip = WORK / f"s{i}.mp4"
        print(f"[commercial2] scene {i + 1}: rendering {scene['duration']}s...", flush=True)
        motion.render_scene(scene, wav, clip, WORK / f"r{i}")
        clips.append(clip)

    full = WORK / "narration_full.wav"
    pieces = []
    for w in audios:
        x, sr = sf.read(str(w), dtype="float32", always_2d=True)
        pieces.append(x.mean(axis=1))
        pieces.append(np.zeros(int(0.3 * sr), dtype=np.float32))
    sf.write(str(full), np.concatenate(pieces).astype(np.float32), 22050)

    print("[commercial2] stitching...", flush=True)
    motion.concat_scenes(clips, full, OUT)
    print(f"[commercial2] DONE: {OUT} ({OUT.stat().st_size // 1024} KB)", flush=True)
    for d in WORK.glob("r*"):
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    main()
