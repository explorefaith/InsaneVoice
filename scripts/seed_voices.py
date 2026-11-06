"""Seed the Voice Library with 70+ preset voices across languages.

Strategy: render ONE natural calibration sentence per language, then derive
multiple preset characters from it with the emotion DSP (pitch / tempo /
spectral tilt) — each variant gets its own speaker embedding + Voice DNA.
Downloads MMS-TTS models for non-MeloTTS languages on first use.

Run:  python scripts/seed_voices.py        (safe to re-run; skips existing)
"""
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

import config  # noqa: E402

config.ensure_dirs()

PRESETS = [
    ("Natural",        {}),
    ("Deep Narrator",  {"pitch": 0.82, "bass_db": 2.0, "tempo": 0.97}),
    ("Warm Baritone",  {"pitch": 0.88, "bass_db": 2.5, "treble_db": -1.0}),
    ("Bright Alto",    {"pitch": 1.10, "treble_db": 2.5}),
    ("Soprano Clear",  {"pitch": 1.22, "treble_db": 3.0}),
    ("Soft Airy",      {"pitch": 0.97, "lowpass": 5200, "tempo": 0.95}),
    ("Fast Energetic", {"pitch": 1.04, "tempo": 1.14, "treble_db": 1.5}),
    ("Slow Cinematic", {"pitch": 0.90, "tempo": 0.90, "bass_db": 1.5}),
]

# language -> (engine, presets subset)
PLAN = {
    "en": ("melo", PRESETS),
    "es": ("melo", PRESETS[:6]),
    "fr": ("melo", PRESETS[:6]),
    "zh": ("melo", PRESETS[:6]),
    "ja": ("melo", PRESETS[:6]),
    "ko": ("mms", PRESETS[:4]),
    "bn": ("mms", PRESETS[:4]),
    "hi": ("mms", PRESETS[:4]),
    "ar": ("mms", PRESETS[:3]),
    "de": ("mms", PRESETS[:3]),
    "pt": ("mms", PRESETS[:3]),
    "ru": ("mms", PRESETS[:3]),
    "it": ("mms", PRESETS[:2]),
    "tr": ("mms", PRESETS[:2]),
    "vi": ("mms", PRESETS[:2]),
    "id": ("mms", PRESETS[:2]),
    "nl": ("mms", PRESETS[:2]),
    "pl": ("mms", PRESETS[:2]),
}


def main():
    import engine
    import langs
    import dna
    import storage
    from emotions import apply_dsp
    import soundfile as sf

    existing = {v.get("preset_key") for v in storage.list_voices()}
    print(f"[seed] existing presets: {len([x for x in existing if x])}", flush=True)

    print("[seed] warming engine...", flush=True)
    engine.ensure_loaded(block=True)

    total = sum(len(p) for _, p in PLAN.values())
    done = 0
    t0 = time.time()

    for lang, (kind, presets) in PLAN.items():
        label = langs.all_lang_list().get(lang, lang)
        sentence = langs.SAMPLE_SENTENCES.get(lang) or langs.SAMPLE_SENTENCES["en"]
        base = config.DATA_DIR / "presets" / f"base_{lang}.wav"
        base.parent.mkdir(parents=True, exist_ok=True)
        if not base.exists():
            print(f"[seed] {label}: rendering base sentence ({kind})...", flush=True)
            try:
                if kind == "melo":
                    engine.ensure_loaded(block=True)
                    with engine._lock:
                        engine._load_tts(lang)
                        tts = engine._tts_pool[lang]
                        spk_ids = dict(tts.hps.data.spk2id)
                        spk = ("EN-US" if lang == "en" else list(spk_ids)[0])
                        tts.tts_to_file(sentence, spk_ids[spk], str(base), speed=1.0)
                else:
                    engine.mms_generate(sentence, langs.MMS_ISO[lang], base)
            except Exception as e:
                print(f"[seed] SKIP {label} — base render failed: {str(e)[:120]}", flush=True)
                total -= len(presets)
                continue
        else:
            print(f"[seed] {label}: base cached", flush=True)

        for pname, params in presets:
            key = f"{lang}:{pname}"
            done += 1
            if key in existing:
                continue
            tag = "EN-US" if (lang == "en" and pname != "British") else ""
            name = f"{label} · {pname}" + (f" ({tag})" if tag else "")
            try:
                shaped = config.DATA_DIR / "presets" / f"v_{lang}_{pname.replace(' ', '_')}.wav"
                apply_dsp(base, shaped, params) if params else shutil_copy(base, shaped)
                report = dna.analyze(str(shaped))
                vid = storage.new_id("ref")
                final_wav = config.SAMPLES_DIR / f"{vid}.wav"
                shutil_copy(shaped, final_wav)
                se_path = config.VOICES_DIR / f"{vid}.pth"
                engine.extract_speaker_embedding(final_wav, se_path)
                profile = {
                    "id": vid, "name": name, "created_at": storage.now(),
                    "sample": final_wav.name,
                    "sample_url": f"/api/audio/samples/{final_wav.name}",
                    "se_path": str(se_path), "duration": report["duration"],
                    "consent": True,
                    "notes": "Built-in preset voice (DSP-shaped base speaker, synthetic origin).",
                    "dna": report, "verified": True, "preset": True,
                    "preset_key": key, "language": lang,
                    "speaker": pname,
                }
                storage.add_voice(profile)
                print(f"[seed] + {name}  ({done}/{total})  f0={report['f0_median']}Hz", flush=True)
            except Exception as e:
                print(f"[seed] FAILED {name}: {str(e)[:140]}", flush=True)

    n = len(storage.list_voices())
    print(f"[seed] DONE in {time.time() - t0:.0f}s — library now has {n} voices", flush=True)


def shutil_copy(a, b):
    import shutil
    shutil.copy(str(a), str(b))


if __name__ == "__main__":
    main()
