"""InsaneVoice - central configuration & path resolution.

Environment overrides:
    INSANEVOICE_HOME   data + models root (default: <repo>/.ivdata)
"""
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent

# third-party engine sources (cloned by setup script)
OPENVOICE_DIR = REPO_ROOT / "third_party" / "OpenVoice"
MELOTTS_DIR = REPO_ROOT / "third_party" / "MeloTTS"

IV_HOME = Path(os.environ.get("INSANEVOICE_HOME", REPO_ROOT / ".ivdata"))
MODELS_DIR = IV_HOME / "models"
DATA_DIR = IV_HOME / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
VOICES_DIR = DATA_DIR / "voices"      # per-voice speaker embeddings (SE)
OUTPUT_DIR = DATA_DIR / "output"      # generated audio
SAMPLES_DIR = DATA_DIR / "samples"    # normalized reference samples

OPENVOICE_CKPT_DIR = MODELS_DIR / "OpenVoiceV2"
MELOTTS_CKPT = MODELS_DIR / "MeloTTS-English" / "checkpoint.pth"
MELOTTS_CONFIG = MODELS_DIR / "MeloTTS-English" / "config.json"

APP_NAME = "InsaneVoice"
VERSION = "1.0.0"

SAMPLE_RATE = 22050          # working rate for analysis + SE extraction
MAX_UPLOAD_MB = 30
MIN_SAMPLE_SECONDS = 4.0     # below this -> quality warning
IDEAL_SAMPLE_SECONDS = 12.0


def ensure_dirs() -> None:
    for d in (IV_HOME, MODELS_DIR, DATA_DIR, UPLOADS_DIR, VOICES_DIR,
              OUTPUT_DIR, SAMPLES_DIR):
        d.mkdir(parents=True, exist_ok=True)


def models_present() -> bool:
    return (OPENVOICE_CKPT_DIR / "converter" / "checkpoint.pth").exists() and MELOTTS_CKPT.exists()


def add_third_party_to_path() -> None:
    """Import engines straight from the cloned repos - no pip -e needed."""
    for p in (str(OPENVOICE_DIR), str(MELOTTS_DIR)):
        if p not in sys.path:
            sys.path.insert(0, p)
