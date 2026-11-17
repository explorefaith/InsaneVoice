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


def _resolve_se(path: str | Path) -> Path:
    """Old profiles may store absolute paths from another machine
    (e.g. a Windows install) - fall back to this machine's voices dir."""
    p = Path(path)
    if p.exists():
        return p
    cand = config.VOICES_DIR / Path(str(path).replace("\\", "/")).name
    if cand.exists():
        return cand
    raise FileNotFoundError(f"Speaker embedding not found: {path}")


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
        st = STATE["status"]
    if block and st == "loading":
        # an async warmup is already loading - wait for it instead of failing
        while True:
            time.sleep(0.25)
            with _lock:
                if STATE["status"] != "loading":
                    break
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
        # VAD-trimmed chunks give a stabler embedding than the raw upload
        # (silence, noise between phrases and long files all skew it)
        chunks: list[Path] = []
        try:
            chunks = _se_chunks(Path(wav_path), save_path.parent)
        except Exception:
            chunks = []
        try:
            _converter.extract_se([str(p) for p in chunks] or [str(wav_path)],
                                  str(save_path))
        finally:
            for c in chunks:
                c.unlink(missing_ok=True)
        return save_path


def _se_chunks(wav_path: Path, tmp_dir: Path, max_chunk_s: float = 10.0) -> list[Path]:
    """Keep only speech (drop silence between phrases), split into <=10s parts."""
    import numpy as np
    import soundfile as sf
    x, sr = sf.read(str(wav_path), dtype="float32", always_2d=True)
    x = x.mean(axis=1)
    fl, hp = int(sr * 0.025), int(sr * 0.010)
    n = max(1, (len(x) - fl) // hp + 1)
    idx = np.arange(fl)[None, :] + hp * np.arange(n)[:, None]
    rms = np.sqrt(np.mean(x[idx] ** 2, axis=1))
    thr = max(0.01, 0.08 * float(np.percentile(rms, 95)))
    voiced = rms >= thr
    d = np.diff(voiced.astype(np.int8))
    starts = np.where(d == 1)[0] + 1
    ends = np.where(d == -1)[0] + 1
    if len(voiced) and voiced[0]:
        starts = np.r_[0, starts]
    if len(voiced) and voiced[-1]:
        ends = np.r_[ends, len(voiced)]
    min_run = int(0.4 / 0.010)
    min_hole = int(0.3 / 0.010)
    merged: list[list[int]] = []
    for a, b in zip(starts, ends):
        if b - a < min_run:
            continue
        if merged and a - merged[-1][1] < min_hole:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    if not merged:
        return []
    speech = np.concatenate([x[a * hp: min(len(x), b * hp + fl)] for a, b in merged])
    speech = speech[:int(30 * sr)]           # embedding needs no more
    chunk_n = int(max_chunk_s * sr)
    out: list[Path] = []
    for k, i in enumerate(range(0, len(speech), chunk_n)):
        cpath = tmp_dir / f"{wav_path.stem}_se{k}.wav"
        sf.write(str(cpath), speech[i:i + chunk_n], sr)
        out.append(cpath)
    return out


def _tts_clause(text: str, lang: str, accent: str | None, speed: float,
                out_path: Path) -> None:
    """Render one clause through the language's base TTS."""
    if langs.is_mms(lang):
        mms_generate(text, langs.MMS_ISO[lang.lower()], out_path, speed=speed)
        return
    _load_tts(lang)
    tts = _tts_pool[lang]
    spk_ids = dict(tts.hps.data.spk2id)
    if lang == "en":
        spk = "EN-US" if (accent in (None, "en-us")) else "EN-BR"
        spk = spk if spk in spk_ids else list(spk_ids)[0]
    else:
        spk = list(spk_ids)[0]
    tts.tts_to_file(text, spk_ids[spk], str(out_path), speed=float(speed))


def _render_prosodic_base(text: str, lang: str, accent: str | None,
                          speed: float, out_path: Path,
                          work_dir: Path, uid: str):
    """Render clause-by-clause with per-phrase intonation, clause micro-gaps,
    final lengthening and per-phrase speed — the closest plain DSP gets to a
    human read. Returns (base_wav_path, sentence_join_times)."""
    import numpy as np
    import soundfile as sf
    import prosody

    rng = np.random.default_rng()
    sentences = prosody.split_sentences(text)
    if len(sentences) < 2:
        raise ValueError("text too short for prosodic assembly")
    sr = config.SAMPLE_RATE
    groups: list[list[np.ndarray]] = []
    tmp_files: list[Path] = []
    for si, sent in enumerate(sentences):
        clauses = prosody.split_clauses(sent)
        group: list[np.ndarray] = []
        for ci, cl in enumerate(clauses):
            tmp = work_dir / f"{uid}_c{si}_{ci}.wav"
            _tts_clause(cl, lang, accent, speed * rng.uniform(0.96, 1.05), tmp)
            x, xsr = sf.read(str(tmp), dtype="float32", always_2d=True)
            x = x.mean(axis=1)
            if xsr != sr:
                import librosa
                x = librosa.resample(x, orig_sr=xsr, target_sr=sr)
            tmp_files.append(tmp)
            last = ci == len(clauses) - 1
            if last:
                kind = "final_rise" if sent.rstrip().endswith("?") else "final_fall"
                x = prosody.final_lengthen(x, sr)
            else:
                kind = "continuation"
            x = prosody.contour_clause(x, sr, kind, rng, intensity=1.15)
            gain_db = rng.uniform(-0.7, 0.7)
            if cl.rstrip().endswith("!"):
                gain_db += 1.3
            x *= 10 ** (gain_db / 20)
            group.append(x)
        groups.append(group)
    y, joins = prosody.assemble(groups, sr, rng)
    sf.write(str(out_path), y, sr)
    for p in tmp_files:
        p.unlink(missing_ok=True)
    return out_path, joins


def generate(text: str, tgt_se_path: str | Path, out_path: str | Path,
             speed: float = 1.0, tau: float = 0.3,
             accent: str | None = None, lang: str = "en",
             humanize: bool = True) -> Path:
    """Full pipeline: text -> base speech -> tone transfer -> final wav.

    lang routing: melo languages (en/es/fr/zh/ja/ko) use the MeloTTS pool;
    MMS languages (bn/hi/ar/...) use facebook/mms-tts with a dynamic
    source embedding taken from the base render itself.

    humanize: add human-like prosody (pitch contours, micro-jitter, breaths,
    room tone) around the tone transfer — the biggest de-robotising step.
    """
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
        STATE["active_lang"] = lang
        STATE["detail"] = f"Speaking {L['label']}..."
        tmp_base = out_path.with_name(out_path.stem + "_base.wav")

        tmp_base = out_path.with_name(out_path.stem + "_base.wav")
        conv_src = tmp_base
        bounds: list = []

        import torch
        tgt_se = torch.load(str(_resolve_se(tgt_se_path)), map_location="cpu", weights_only=True)

        # human-like delivery BEFORE the tone transfer: the converter only
        # borrows timbre, so whatever rhythm/intonation the base carries
        # survives into the clone.
        rendered_prosodic = False
        if humanize:
            try:
                STATE["detail"] = "Shaping phrase prosody..."
                conv_src, bounds = _render_prosodic_base(
                    text, lang, accent, speed, tmp_base,
                    work_dir=out_path.parent, uid=out_path.stem)
                rendered_prosodic = True
                print(f"[prosody] per-clause render: {len(bounds)} sentence joins",
                      flush=True)
            except Exception as e:
                print(f"[prosody] per-clause render failed ({e}); single render",
                      flush=True)
                conv_src, bounds = tmp_base, []
        if not rendered_prosodic:
            if langs.is_mms(lang):
                mms_generate(text, langs.MMS_ISO[lang.lower()], tmp_base, speed=speed)
            else:
                _load_tts(lang)
                tts = _tts_pool[lang]
                spk_ids = dict(tts.hps.data.spk2id)
                if lang == "en":
                    spk = "EN-US" if (accent in (None, "en-us")) else "EN-BR"
                    spk = spk if spk in spk_ids else list(spk_ids)[0]
                else:
                    spk = list(spk_ids)[0]
                tts.tts_to_file(text, spk_ids[spk], str(tmp_base), speed=float(speed))
            if humanize:
                # fallback: contour the single render at sentence level
                try:
                    import prosody
                    hum = out_path.with_name(out_path.stem + "_hum.wav")
                    bounds = prosody.humanize(tmp_base, hum,
                                              sentences=prosody.split_sentences(text))
                    conv_src = hum
                    print(f"[prosody] contour pass: {len(bounds)} joins", flush=True)
                except Exception as e:
                    print(f"[prosody] pre-pass skipped: {e}", flush=True)
                    conv_src, bounds = tmp_base, []

        if langs.is_mms(lang):
            # dynamic source embedding from the (humanised) base render
            src_tmp = out_path.with_name(out_path.stem + "_srcse.pth")
            _converter.extract_se([str(conv_src)], str(src_tmp))
            src_se = torch.load(str(src_tmp), map_location="cpu", weights_only=True)
            src_tmp.unlink(missing_ok=True)
        else:
            src_se = _src_se(lang, accent if lang == "en" else None)
        _converter.convert(audio_src_path=str(conv_src),
                           src_se=src_se, tgt_se=tgt_se,
                           output_path=str(out_path),
                           tau=float(tau), message="InsaneVoice")

        # recorded-room finish AFTER conversion (breaths + room tone), since
        # the converter would otherwise re-vocode them into artifacts
        if humanize and bounds:
            try:
                import prosody
                prosody.finish(str(out_path), str(out_path), bounds)
                print(f"[prosody] finish pass: breaths", flush=True)
            except Exception as e:
                print(f"[prosody] finish skipped: {e}", flush=True)

        for p in (tmp_base, conv_src):
            try:
                Path(p).unlink(missing_ok=True)
            except OSError:
                pass
        STATE["detail"] = "Engine ready."
        print(f"[engine] generated {lang} in {time.time() - t0:.1f}s -> {out_path.name}", flush=True)
        return out_path


# ---------------- MMS (Meta) multilingual base TTS ----------------

_mms_cache: "OrderedDict[str, tuple]" = OrderedDict()
MMS_MAX = 2


def mms_generate(text: str, iso: str, out_path: str | Path, speed: float = 1.0) -> Path:
    """Render base speech with facebook/mms-tts-<iso> (downloads on first use)."""
    import torch
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        if iso not in _mms_cache:
            STATE["detail"] = f"Preparing MMS-{iso} model (first use downloads ~150MB)..."
            print(f"[engine] loading MMS model mms-tts-{iso}", flush=True)
            from transformers import VitsModel, AutoTokenizer
            name = f"facebook/mms-tts-{iso}"
            model = VitsModel.from_pretrained(name)
            tok = AutoTokenizer.from_pretrained(name)
            model.eval()
            _mms_cache[iso] = (model, tok)
            while len(_mms_cache) > MMS_MAX:
                _mms_cache.popitem(last=False)
        model, tok = _mms_cache[iso]
        inputs = tok(text, return_tensors="pt")
        with torch.no_grad():
            wave = model(**inputs).waveform.squeeze().numpy()
        import soundfile as sf
        tmp16 = out_path.with_name(out_path.stem + "_16k.wav")
        sf.write(str(tmp16), wave, model.config.sampling_rate)
        # 16k -> 22050 mono, with optional tempo fit
        import subprocess
        af = "anull"
        if abs(speed - 1.0) > 1e-3:
            v = min(2.0, max(0.5, speed))
            af = f"atempo={v:.4f}"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(tmp16),
                        "-af", af, "-ar", "22050", "-ac", "1", str(out_path)],
                       check=True, capture_output=True, timeout=600)
        tmp16.unlink(missing_ok=True)
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
        tgt_se = torch.load(str(_resolve_se(tgt_se_path)), map_location="cpu", weights_only=True)
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
