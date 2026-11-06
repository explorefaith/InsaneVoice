"""Render the InsaneVoice commercial — entirely with InsaneVoice.

Voice: the library's cloned demo voice. Visuals: InsaneVoice's own motion
engine (the same one the Agent Studio uses). No cloud, no external model.
"""
import sys
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

import config  # noqa: E402

config.ensure_dirs()

WORK = REPO / "docs" / "_commercial_work"
WORK.mkdir(parents=True, exist_ok=True)
OUT_DIR = config.OUTPUT_DIR

SCENES = [
    {"type": "title", "text": "Your voice. Cloned. Free.",
     "sub": "InsaneVoice", "narration": "Your voice. Cloned. Free. InsaneVoice."},
    {"type": "points", "text": "A full voice studio, on your laptop",
     "points": ["Cloning — free forever", "Private — one hundred percent local",
                "Open source — MIT"],
     "narration": "InsaneVoice turns your laptop into a full voice studio. "
                  "No cloud. No subscription. No limits."},
    {"type": "title", "text": "Voice DNA",
     "sub": "pitch · warmth · brightness · grit",
     "narration": "Voice DNA reads your fingerprint: pitch, warmth, brightness "
                  "and grit, then names your voice like a species."},
    {"type": "quote", "text": "Three takes. One winner.",
     "sub": "Director's Studio",
     "narration": "Ten seconds of you is enough. The Director cuts your script "
                  "into chunks and renders three takes for every line. You pick the winner."},
    {"type": "points", "text": "Everything ElevenLabs charges for",
     "points": ["Six languages · emotion tags · sighs, gasps, whispers",
                "Voice changer · performance transfer · isolator",
                "Transcribe · dub videos · long-form projects",
                "Agent Studio — one prompt, whole video"],
     "narration": "Speak six languages. Inject sighs, gasps and whispers. "
                  "Swap any performance into any voice. Isolate, transcribe and dub "
                  "videos, all offline."},
    {"type": "title", "text": "Agent Studio",
     "sub": "one prompt → script → scenes → rendered video",
     "narration": "And the Agent Studio writes the script, voices every scene, "
                  "and renders the whole video from one single prompt."},
    {"type": "end", "text": "InsaneVoice",
     "narration": "InsaneVoice. Your voice. Yours."},
]


def main():
    import soundfile as sf
    import numpy as np
    import engine
    import motion
    from storage import get_voice

    print("[commercial] warming engine...", flush=True)
    engine.ensure_loaded(block=True)
    voice = get_voice("ref_848b496170")
    if not voice:
        raise SystemExit("demo voice missing")

    clips, audios, dur_log = [], [], []
    for i, sc in enumerate(SCENES):
        wav = WORK / f"n{i}.wav"
        print(f"[commercial] scene {i + 1}/{len(SCENES)}: voicing...", flush=True)
        engine.generate(sc["narration"], voice["se_path"], wav, speed=1.02, tau=0.3)
        dur = sf.info(str(wav)).duration
        scene = {k: v for k, v in sc.items() if k not in ("narration",)}
        scene["duration"] = round(dur + 0.5, 2)
        dur_log.append((i + 1, round(dur, 1)))
        audios.append(wav)
        clip = WORK / f"s{i}.mp4"
        print(f"[commercial] scene {i + 1}: rendering {scene['duration']}s...", flush=True)
        motion.render_scene(scene, wav, clip, WORK / f"r{i}")
        clips.append(clip)

    full = WORK / "narration_full.wav"
    pieces = []
    for w in audios:
        x, sr = sf.read(str(w), dtype="float32", always_2d=True)
        pieces.append(x.mean(axis=1))
        pieces.append(np.zeros(int(0.35 * sr), dtype=np.float32))
    sf.write(str(full), np.concatenate(pieces).astype(np.float32), 22050)

    final = OUT_DIR / "InsaneVoice_Commercial.mp4"
    print("[commercial] stitching...", flush=True)
    motion.concat_scenes(clips, full, final)
    size = final.stat().st_size // 1024
    print(f"[commercial] DONE: {final} ({size} KB)  scene durs: {dur_log}", flush=True)
    # cleanup frames
    for d in WORK.glob("r*"):
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    main()
