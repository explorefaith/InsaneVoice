"""Download InsaneVoice model checkpoints from HuggingFace (~330MB total).

Run from anywhere:  python scripts/download_models.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

import config  # noqa: E402

JOBS = [
    # (hf_repo, allow_patterns, dest_subdir)
    ("myshell-ai/OpenVoiceV2", ["checkpoints_v2/**"], "OpenVoiceV2"),
    ("myshell-ai/MeloTTS-English", ["checkpoint.pth", "config.json"], "MeloTTS-English"),
]


def main() -> int:
    config.ensure_dirs()
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("huggingface_hub missing.  pip install huggingface_hub")
        return 1

    for repo, patterns, sub in JOBS:
        dest = config.MODELS_DIR / sub
        dest.mkdir(parents=True, exist_ok=True)
        if sub == "OpenVoiceV2" and (dest / "checkpoints_v2" / "converter" / "checkpoint.pth").exists():
            print(f"[skip] {repo} already present")
            continue
        if sub == "MeloTTS-English" and (dest / "checkpoint.pth").exists():
            print(f"[skip] {repo} already present")
            continue
        print(f"[get ] {repo} -> {dest}")
        t0 = time.time()
        snapshot_download(
            repo_id=repo,
            allow_patterns=patterns,
            local_dir=str(dest),
            max_workers=4,
        )
        print(f"[done] {repo} in {time.time() - t0:.0f}s")

    # NLTK data for g2p_en (English grapheme->phoneme)
    import nltk
    for pkg in ("averaged_perceptron_tagger", "averaged_perceptron_tagger_eng", "cmudict"):
        try:
            nltk.download(pkg, quiet=True)
        except Exception as e:
            print(f"[warn] nltk {pkg}: {e}")

    print("\nAll models ready." if config.models_present() else "\nSome models missing!")
    return 0 if config.models_present() else 2


if __name__ == "__main__":
    raise SystemExit(main())
