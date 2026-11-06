"""InsaneVoice — cloning engine v2.

Pipeline (all local, all free):
    MeloTTS (multi-language base TTS, CPU)
        -> OpenVoice V2 ToneColorConverter (transfers YOUR voice's tone)

v2 adds:
    - language pool: EN/ES/FR/ZH/JA/KO base models, lazy-loaded with LRU
      (8 GB laptops cannot hold every language at once)
    - convert_audio(): pure audio->audio tone transfer (Voice Changer /
      performance transfer) without any text-to-speech
    - per-language source speaker embeddings
"""
from __future__ import annotations

import os
import threading
import time
import traceback
from collections import OrderedDict
from pathlib import Path

import config
import langs

STATE = {
    "status": "unloaded",       # unloaded | loading | ready | error
    "detail": "Engine loads on first use.",
    "loaded_at": None,
    "error": None,
    "loaded_langs": [],
    "active_lang": None,
}

_lock = threading.RLock()
_converter = None
_tts_pool: "OrderedDict[str, object]" = OrderedDict()   # lang -> MeloTTS TTS
_SE_CACHE: dict[str, object] = {}                      # "en-us" etc -> tensor
POOl_MAX = 2          # base TTS models kept in RAM at once (EN + one more)


def status() -> dict:
    return dict(STATE)


def _load_converter():
    global _converter
    if _converter is not None:
        return
    import torch
    from openvoice.api import ToneColorConverter

    torch.set_num_threads(max(1, min(8, os.cpu_count() or 4)))

    ckpt_dir = config.OPENVOICE_CKPT_DIR
    conv_ckpt = ckpt_dir / "converter" / "checkpoint.pth"
    conv_cfg = ckpt_dir / "converter" / "config.json"
    if not conv_ckpt.exists():
        raise RuntimeError(f"Tone converter checkpoint missing: {conv_ckpt}. "
                           f"Run scripts/download_models.py first.")
    _converter = ToneColorConverter(str(conv_cfg), device="cpu")
    _converter.load_ckpt(str(conv_ckpt))


def _load_tts(lang: str):
    """Load (or fetch from pool) the MeloTTS model for a language."""
    global _tts_pool
    if lang in _tts_pool:
        _tts_pool.move_to_end(lang)
        return _tts_pool[lang]

    from melo.api import TTS

    L = langs.get(lang)
    if lang == "en":
        if not config.MELOTTS_CKPT.exists():
            raise RuntimeError(f"MeloTTS checkpoint missing: {config.MELOTTS_CKPT}")
        tts = TTS(language=L["melo"], device="cpu",
                  config_path=str(config.MELOTTS_CONFIG),
                  ckpt_path=str(config.MELOTTS_CKPT))
    else:
        # other languages download their checkpoints on first use (cached)
        STATE["detail"] = f"Preparing {L['label']} base model (first use downloads ~170MB)..."
        print(f"[engine] loading {L['label']} TTS (may download checkpoint)", flush=True)
        tts = TTS(language=L["melo"], device="cpu")

    _tts_pool[lang] = tts
    while len(_tts_pool) > POOl_MAX:
        evicted, _ = _tts_pool.popitem(last=False)
        print(f"[engine] evicted {evicted} model from RAM", flush=True)
    STATE["loaded_langs"] = list(_tts_pool.keys())
    STATE["active_lang"] = lang
    return tts


def _src_se(lang: str, accent: str | None):
    import torch
    key = langs.ses_key(lang, accent)
    if key not in _SE_CACHE:
        p = config.OPENVOICE_CKPT_DIR / "base_speakers" / "ses" / f"{key}.pth"
        if not p.exists():
            raise RuntimeError(f"Base speaker embedding missing: {p}")
        _SE_CACHE[key] = torch.load(str(p), map_location="cpu", weights_only=True)
    return _SE_CACHE[key]


def _load():
    try:
        STATE.update(status="loading",
                     detail="Loading tone converter + English base TTS...",
                     error=None)
        config.add_third_party_to_path()
        _load_converter()
        _load_tts("en")
        STATE.update(status="ready", loaded_at=time.time(),
                     detail="Engine ready.", error=None,
                     loaded_langs=list(_tts_pool.keys()), active_lang="en")
        print("[engine] ready", flush=True)
    except Exception as e:  # pragma: no cover
        STATE.update(status="error", error=f"{e}\n{traceback.format_exc()[:1200]}",
                     detail="Engine failed to load.")
        print("[engine] FAILED:", e, flush=True)


def ensure_loaded(block: bool = True) -> dict:
    with _lock:
        if STATE["status"] in ("unloaded", "error"):
            STATE["status"] = "loading"
            if block:
                _load()
            else:
                threading.Thread(target=_load, daemon=True).start()
        return status()


def warmup_async() -> None:
    ensure_loaded(block=False)


def extract_speaker_embedding(wav_path: str | Path, save_path: str | Path) -> Path:
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
             accent: str | None = None, lang: str = "en") -> Path:
    """Full pipeline: text -> base speech -> tone transfer -> final wav."""
    global _converter
    ensure_loaded(block=True)
    if STATE["status"] != "ready":
        raise RuntimeError(f"Engine not ready: {STATE.get('error') or STATE['detail']}")
    text = (text or "").strip()
    if not text:
        raise ValueError("Text is empty.")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    L = langs.get(lang)
    with _lock:
        t0 = time.time()
        _load_tts(lang)
        STATE["active_lang"] = lang
        STATE["detail"] = f"Speaking {L['label']}..."
        tmp_base = out_path.with_name(out_path.stem + "_base.wav")

        tts = _tts_pool[lang]
        spk_ids = tts.hps.data.spk2id
        if lang == "en":
            spk = "EN-US" if (accent in (None, "en-us")) else "EN-BR"
            spk = spk if spk in spk_ids else list(spk_ids)[0]
        else:
            spk = list(spk_ids)[0]
        tts.tts_to_file(text, spk_ids[spk], str(tmp_base), speed=float(speed))

        import torch
        tgt_se = torch.load(str(tgt_se_path), map_location="cpu", weights_only=True)
        _converter.convert(audio_src_path=str(tmp_base),
                           src_se=_src_se(lang, accent if lang == "en" else None),
                           tgt_se=tgt_se,
                           output_path=str(out_path),
                           tau=float(tau), message="InsaneVoice")
        try:
            tmp_base.unlink(missing_ok=True)
        except OSError:
            pass
        STATE["detail"] = "Engine ready."
        print(f"[engine] generated {lang} in {time.time() - t0:.1f}s -> {out_path.name}", flush=True)
        return out_path


def convert_audio(audio_src_path: str | Path, tgt_se_path: str | Path,
                  out_path: str | Path, tau: float = 0.3) -> Path:
    """Voice changer: keep the PERFORMANCE, borrow the TONE.

    Works on any language / any recording - no TTS involved.
    """
    global _converter
    ensure_loaded(block=True)
    if STATE["status"] != "ready":
        raise RuntimeError(f"Engine not ready: {STATE.get('error') or STATE['detail']}")
    import torch
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        t0 = time.time()
        tgt_se = torch.load(str(tgt_se_path), map_location="cpu", weights_only=True)
        # source SE = the incoming recording itself (performance carrier)
        src_tmp = out_path.with_name(out_path.stem + "_srcse.pth")
        _converter.extract_se([str(audio_src_path)], str(src_tmp))
        src_se = torch.load(str(src_tmp), map_location="cpu", weights_only=True)
        _converter.convert(audio_src_path=str(audio_src_path),
                           src_se=src_se, tgt_se=tgt_se,
                           output_path=str(out_path),
                           tau=float(tau), message="InsaneVoice")
        try:
            src_tmp.unlink(missing_ok=True)
        except OSError:
            pass
        print(f"[engine] voice-changed in {time.time() - t0:.1f}s -> {out_path.name}", flush=True)
        return out_path
