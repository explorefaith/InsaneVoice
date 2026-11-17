"""InsaneVoice — local translation for DubHub.

NLLB-200 (Meta, distilled 600M) runs fully offline: any of 200 languages
to any other. Weights (~1.2 GB) download once on first use and live in the
HF cache, like every other model in this app.
"""
from __future__ import annotations

import threading
from collections import OrderedDict

_lock = threading.RLock()
_tok = None
_model = None

NAME = "facebook/nllb-200-distilled-600M"

# our lang codes -> NLLB flores-200 codes
FLORES = {
    "en": "eng_Latn", "es": "spa_Latn", "fr": "fra_Latn", "zh": "zho_Hans",
    "ja": "jpn_Jpan", "ko": "kor_Hang", "bn": "ben_Beng", "hi": "hin_Deva",
    "ar": "arb_Arab", "de": "deu_Latn", "pt": "por_Latn", "ru": "rus_Cyrl",
    "it": "ita_Latn", "tr": "tur_Latn", "vi": "vie_Latn", "id": "ind_Latn",
    "nl": "nld_Latn", "pl": "pol_Latn", "ur": "urd_Arab", "ta": "tam_Taml",
    "te": "tel_Telu", "mr": "mar_Deva", "gu": "guj_Gujr", "kn": "kan_Knda",
    "pa": "pan_Guru", "ne": "nep_Deva", "as": "asm_Beng", "or": "orya_Orya",
    "si": "sin_Sinh", "sw": "swh_Latn", "th": "tha_Thai", "fil": "fil_Latn",
}

BATCH = 8


def supported() -> dict:
    """{lang_code: flores_code} pairs DubHub can translate between."""
    return dict(FLORES)


def _load():
    global _tok, _model
    with _lock:
        if _model is not None:
            return _tok, _model
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        torch.set_num_threads(max(1, min(8, __import__("os").cpu_count() or 4)))
        tok = AutoTokenizer.from_pretrained(NAME)
        model = AutoModelForSeq2SeqLM.from_pretrained(NAME)
        model.eval()
        _tok, _model = tok, model
        return _tok, _model


def translate_lines(lines: list[str], src: str, tgt: str,
                    progress=None) -> list[str]:
    """Translate a list of lines src -> tgt, preserving order and blanks."""
    src_c, tgt_c = FLORES.get((src or "").lower()), FLORES.get((tgt or "").lower())
    if not src_c or not tgt_c:
        raise ValueError(f"Unsupported language pair: {src!r} -> {tgt!r}")
    if src_c == tgt_c:
        return list(lines)

    import torch
    tok, model = _load()
    clean = [(l or "").strip() for l in lines]
    out: list[str] = [""] * len(clean)
    total = len(clean)
    done = 0
    with _lock:
        for start in range(0, total, BATCH):
            chunk = clean[start:start + BATCH]
            idx = [i for i, l in enumerate(chunk) if l]
            batch = [chunk[i] for i in idx] or [""]
            enc = tok(batch, return_tensors="pt", padding=True, truncation=True,
                      max_length=380, src_lang=src_c)
            with torch.no_grad():
                gen = model.generate(**enc, forced_bos_token_id=tok.convert_tokens_to_ids(tgt_c),
                                     max_new_tokens=300, num_beams=1)
            dec = tok.batch_decode(gen, skip_special_tokens=True)
            for i, text in zip(idx, dec):
                out[start + i] = text.strip()
            done += len(chunk)
            if progress:
                progress(min(1.0, done / total))
    return out
