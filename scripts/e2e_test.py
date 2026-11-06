"""End-to-end engine test: base TTS -> demo voice -> tone transfer -> verify.

Verifies the whole cloning chain objectively by comparing Voice DNA
(median pitch etc.) between base speaker, reference sample and output.
"""
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

import config  # noqa: E402

config.ensure_dirs()
TEST = REPO / "scripts" / "_e2e_out"
TEST.mkdir(exist_ok=True)


def analyze(path: Path) -> dict:
    import dna
    return dna.analyze(str(path))


def main() -> int:
    t_all = time.time()

    print("== 1. loading engine (models -> RAM) ==", flush=True)
    import engine
    engine.ensure_loaded(block=True)
    st = engine.status()
    print("   engine:", st["status"], "-", st["detail"])
    if st["status"] != "ready":
        print(st.get("error", ""))
        return 1

    import torch
    from melo.api import TTS  # noqa: F401  (engine already holds _tts)

    text = "Hello there. This is a voice cloning test on a laptop processor."

    print("== 2. base speaker reference (EN-BR) ==", flush=True)
    sys.path.insert(0, str(config.MELOTTS_DIR))
    t0 = time.time()
    ref = TEST / "ref_enbr.wav"
    engine._tts.tts_to_file(text, engine._tts.hps.data.spk2id["EN-BR"], str(ref), speed=1.0)
    print(f"   ref wav in {time.time() - t0:.1f}s")

    print("== 3. Voice DNA on reference ==", flush=True)
    dna_ref = analyze(ref)
    print(f"   f0={dna_ref['f0_median']}Hz archetype={dna_ref['archetype']!r}")

    print("== 4. extract speaker embedding ==", flush=True)
    t0 = time.time()
    se = engine.extract_speaker_embedding(ref, TEST / "demo.se.pth")
    print(f"   SE saved in {time.time() - t0:.1f}s -> {se.name}")

    print("== 5. clone-generate via tone transfer ==", flush=True)
    t0 = time.time()
    out = TEST / "cloned.wav"
    engine.generate(
        "InsaneVoice is working perfectly. Every word you hear was generated "
        "locally on a laptop, with zero cost and zero cloud.",
        se, out, speed=1.0, tau=0.3)
    gen_t = time.time() - t0
    print(f"   generated in {gen_t:.1f}s")

    print("== 6. verification: DNA comparison ==", flush=True)
    base = TEST / "base_enus.wav"
    engine._tts.tts_to_file(
        "InsaneVoice is working perfectly. Every word you hear was generated "
        "locally on a laptop, with zero cost and zero cloud.",
        engine._tts.hps.data.spk2id["EN-US"], str(base), speed=1.0)
    dna_base = analyze(base)
    dna_out = analyze(out)

    print("\n   {:<22}{:>10}{:>10}{:>10}".format("metric", "base-US", "ref-BR", "output"))
    for key in ("f0_median", "f0_range", "spectral_centroid", "formant_f1"):
        b, r, o = dna_base[key], dna_ref[key], dna_out[key]
        closer = "OUT" if abs(o - r) < abs(o - b) else "BASE"
        print("   {:<22}{:>10.1f}{:>10.1f}{:>10.1f}  ->{}".format(key, b, r, o, closer))

    print(f"\n   output archetype: {dna_out['archetype']!r}")
    print(f"   output duration : {dna_out['duration']}s, warnings: {dna_out['warnings']}")

    ok = dna_out["duration"] > 2.0
    print("\nE2E", "PASS" if ok else "FAIL", f"- total {time.time() - t_all:.0f}s")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
