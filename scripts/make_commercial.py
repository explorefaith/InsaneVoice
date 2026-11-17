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
    dict(type="title", text="Paying to sound like yourself?",
         sub="InsaneVoice — a free, local voice studio",
         narration="Still paying every month, just to sound like yourself?"),
    dict(type="points", text="The problem",
         points=["Rented voices, monthly bills", "Flat, robotic delivery",
                 "Your audio lives on someone else's cloud"],
         narration="Robotic voices, rental voices, and your audio living on someone else's cloud."),
    dict(type="ui_record",
         path=[(900, 620), (735, 300), (735, 300)], clicks=[0.22, 0.8],
         sfx=[{"t": 0.22, "k": "click"}, {"t": 0.27, "k": "whoosh"},
              {"t": 0.55, "k": "type"}, {"t": 0.62, "k": "type"},
              {"t": 0.8, "k": "click"}],
         narration="InsaneVoice runs on your own laptop. Record yourself for just ten seconds."),
    dict(type="ui_clone",
         path=[(900, 620), (700, 380)], clicks=[0.15],
         sfx=[{"t": 0.15, "k": "click"}, {"t": 0.55, "k": "chime"}],
         narration="Voice DNA reads your fingerprint. The cloner paints every word with your tone."),
    dict(type="ui_generate",
         path=[(900, 620), (400, 200), (396, 333)], clicks=[0.42],
         sfx=[{"t": 0.06 + i * 0.045, "k": "type"} for i in range(14)]
             + [{"t": 0.42, "k": "click"}, {"t": 0.88, "k": "success"}],
         narration="Type anything. Add sighs, gasps, whispers, then press generate.",
         typed_text="Add [sigh] sighs, [gasp] gasps, [happy] joy, [whisper] secrets!"),
    dict(type="ui_language", sel_idx=6, sel_t=0.6,
         path=[(900, 620), (450, 320), (450, 398)], clicks=[0.18, 0.6],
         sfx=[{"t": 0.18, "k": "click"}, {"t": 0.4, "k": "whoosh"},
              {"t": 0.6, "k": "click"}, {"t": 0.68, "k": "pop"}],
         narration="আর ভাষা? বাংলা, হিন্দি, আরবি — সবকিছু সম্পূর্ণ অফলাইনে!"),
    dict(type="ui_voices",
         path=[(900, 620), (450, 300)], clicks=[],
         sfx=[{"t": 0.18, "k": "whoosh"}, {"t": 0.75, "k": "chime"}],
         narration="Seventy plus ready voices, across sixteen languages, every one free."),
    dict(type="ui_connections",
         path=[(900, 620), (500, 282), (500, 282)], clicks=[0.3],
         sfx=[{"t": 0.3, "k": "click"}]
             + [{"t": 0.44 + i * 0.04, "k": "type"} for i in range(6)]
             + [{"t": 0.68, "k": "success"}],
         narration="Bring your own model. Paste a key. Add fallbacks. Keys never leave this machine."),
    dict(type="ui_agent",
         path=[(900, 620), (390, 230)], clicks=[0.28],
         sfx=[{"t": 0.28, "k": "click"}]
             + [{"t": 0.44 + i * 0.09, "k": "pop"} for i in range(4)]
             + [{"t": 0.92, "k": "chime"}],
         narration="The Agent Studio writes, voices, and renders a full video from one prompt."),
    dict(type="points", text="Proof, not promises",
         points=["No cloud. No API keys. No bills.",
                 "Consent gate + inaudible watermark",
                 "Open source under MIT"],
         narration="No cloud, no keys, no bills. Consent gated and watermarked."),
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

    host = pick_voice(lambda v: v.get("id") == "ref_848b496170")         or pick_voice(lambda v: "Demo British" in v.get("name", ""))         or pick_voice(lambda v: v.get("language") == "en" and v.get("preset"))
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
                        speed=1.12, tau=0.3, lang=lang)
        dur = sf.info(str(wav)).duration
        scene = dict(sc)
        scene["duration"] = round(dur + 0.4, 2)
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
