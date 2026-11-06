"""InsaneVoice - cloning engine.

Pipeline (all local, all free):
    MeloTTS (EN base TTS, CPU)  ->  OpenVoice V2 ToneColorConverter
                                       (transfers YOUR voice's tone)

Engine loads lazily on first use and is guarded by a lock - generation
requests from multiple tabs queue up politely.
"""
from __future__ import annotations

import threading
import time
import traceback
from pathlib import Path

import config

STATE = {
    "status": "unloaded",       # unloaded | loading | ready | error
    "detail": "Engine loads on first use.",
    "loaded_at": None,
    "error": None,
}

_lock = threading.RLock()
_converter = None
_tts = None
_src_se = None                     # en-us base speaker embedding
BASE_SPEAKERS = {"en-us": "American (EN-US)", "en-br": "British (EN-BR)"}


def status() -> dict:
    return dict(STATE)


def _load():
    global _converter, _tts, _src_se
    if STATE["status"] == "ready":
        return
    STATE.update(status="loading",
                 detail="Loading tone converter + base TTS models into memory...",
                 error=None)
    try:
        config.add_third_party_to_path()
        import torch
        from openvoice.api import ToneColorConverter
        from melo.api import TTS

        torch.set_num_threads(max(1, min(8, __import__("os").cpu_count() or 4)))

        ckpt_dir = config.OPENVOICE_CKPT_DIR
        conv_ckpt = ckpt_dir / "converter" / "checkpoint.pth"
        conv_cfg = ckpt_dir / "converter" / "config.json"
        if not conv_ckpt.exists():
            raise RuntimeError(f"Tone converter checkpoint missing: {conv_ckpt}. "
                               f"Run scripts/download_models.py first.")

        _converter = ToneColorConverter(str(conv_cfg), device="cpu")
        _converter.load_ckpt(str(conv_ckpt))

        se_path = ckpt_dir / "base_speakers" / "ses" / "en-us.pth"
        _src_se = torch.load(str(se_path), map_location="cpu", weights_only=True)

        if not config.MELOTTS_CKPT.exists():
            raise RuntimeError(f"MeloTTS checkpoint missing: {config.MELOTTS_CKPT}. "
                               f"Run scripts/download_models.py first.")
        _tts = TTS(language="EN", device="cpu",
                   config_path=str(config.MELOTTS_CONFIG),
                   ckpt_path=str(config.MELOTTS_CKPT))

        STATE.update(status="ready", loaded_at=time.time(),
                     detail="Engine ready.", error=None)
        print("[engine] ready", flush=True)
    except Exception as e:  # pragma: no cover
        STATE.update(status="error", error=f"{e}\n{traceback.format_exc()[:1200]}",
                     detail="Engine failed to load.")
        print("[engine] FAILED:", e, flush=True)


def ensure_loaded(block: bool = True) -> dict:
    """Trigger lazy load. If block=True, wait until ready/error."""
    with _lock:
        if STATE["status"] in ("unloaded", "error"):
            STATE["status"] = "loading"
            if block:
                _load()
            else:
                threading.Thread(target=_load, daemon=True).start()
        if block and STATE["status"] == "loading":
            # another thread may be loading; wait for the lock then recheck
            pass
        return status()


def warmup_async() -> None:
    ensure_loaded(block=False)


def extract_speaker_embedding(wav_path: str | Path, save_path: str | Path) -> Path:
    """Compute OpenVoice SE for a reference wav and save it."""
    global _converter
    ensure_loaded(block=True)
    if STATE["status"] != "ready":
        raise RuntimeError(f"Engine not ready: {STATE.get('error') or STATE['detail']}")
    with _lock:
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        _converter.extract_se([str(wav_path)], str(save_path))
        return save_path


def generate(text: str, tgt_se_path: str | Path, out_path: str | Path,
             speed: float = 1.0, tau: float = 0.3,
             accent: str = "en-us") -> Path:
    """Full pipeline: text -> base speech -> tone transfer -> final wav."""
    global _converter, _tts, _src_se
    ensure_loaded(block=True)
    if STATE["status"] != "ready":
        raise RuntimeError(f"Engine not ready: {STATE.get('error') or STATE['detail']}")
    text = (text or "").strip()
    if not text:
        raise ValueError("Text is empty.")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with _lock:
        t0 = time.time()
        tmp_base = out_path.with_name(out_path.stem + "_base.wav")
        spk_ids = _tts.hps.data.spk2id
        spk = accent if accent in spk_ids else ("EN-US" if "EN-US" in spk_ids else list(spk_ids)[0])
        _tts.tts_to_file(text, spk_ids[spk], str(tmp_base), speed=float(speed))

        import torch
        tgt_se = torch.load(str(tgt_se_path), map_location="cpu", weights_only=True)
        src_se = _src_se if accent == "en-us" else torch.load(
            str(config.OPENVOICE_CKPT_DIR / "base_speakers" / "ses" / f"{accent}.pth"),
            map_location="cpu", weights_only=True)

        _converter.convert(audio_src_path=str(tmp_base),
                           src_se=src_se, tgt_se=tgt_se,
                           output_path=str(out_path),
                           tau=float(tau), message="InsaneVoice")
        try:
            tmp_base.unlink(missing_ok=True)
        except OSError:
            pass
        print(f"[engine] generated in {time.time() - t0:.1f}s -> {out_path.name}", flush=True)
        return out_path
