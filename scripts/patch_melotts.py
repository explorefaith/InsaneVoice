"""Patch MeloTTS to load only what English inference needs.

Two surgical, idempotent edits:
 1. melo/text/cleaner.py  -> import language modules lazily (kills eager
    Japanese/French/Korean/Chinese BERT downloads at import time)
 2. melo/text/english.py  -> lazy bert-base-uncased tokenizer (fetched on
    first generate, not at import)

Run:  python scripts/patch_melotts.py
"""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MEL = REPO / "third_party" / "MeloTTS" / "melo" / "text"

LAZY_CLEANER = '''import copy

from . import cleaned_text_to_sequence

_cached = {}


def _lang_mod(name):
    if name not in _cached:
        if name == "ZH":
            from . import chinese as mod
        elif name == "JP":
            from . import japanese as mod
        elif name == "EN":
            from . import english as mod
        elif name == "ZH_MIX_EN":
            from . import chinese_mix as mod
        elif name == "KR":
            from . import korean as mod
        elif name == "FR":
            from . import french as mod
        elif name in ("SP", "ES"):
            from . import spanish as mod
        else:
            raise ValueError(f"unsupported language {name}")
        _cached[name] = mod
    return _cached[name]


def clean_text(text, language):
    language_module = _lang_mod(language)
    norm_text = language_module.text_normalize(text)
    phones, tones, word2ph = language_module.g2p(norm_text)
    return norm_text, phones, tones, word2ph


def clean_text_bert(text, language, device=None):
    language_module = _lang_mod(language)
    norm_text = language_module.text_normalize(text)
    phones, tones, word2ph = language_module.g2p(norm_text)

    word2ph_bak = copy.deepcopy(word2ph)
    for i in range(len(word2ph)):
        word2ph[i] = word2ph[i] * 2
    word2ph[0] += 1
    bert = language_module.get_bert_feature(norm_text, word2ph, device=device)

    return norm_text, phones, tones, word2ph_bak, bert


def text_to_sequence(text, language):
    norm_text, phones, tones, word2ph = clean_text(text, language)
    return cleaned_text_to_sequence(phones, tones, language)
'''

ENGLISH_TOKENIZER_OLD = """model_id = 'bert-base-uncased'
tokenizer = AutoTokenizer.from_pretrained(model_id)
def g2p_old(text):"""

ENGLISH_TOKENIZER_NEW = """model_id = 'bert-base-uncased'
tokenizer = None


def _get_tokenizer():
    global tokenizer
    if tokenizer is None:
        tokenizer = AutoTokenizer.from_pretrained(model_id)
    return tokenizer


def g2p_old(text):"""

ENGLISH_G2P_OLD = """def g2p(text, pad_start_end=True, tokenized=None):
    if tokenized is None:
        tokenized = tokenizer.tokenize(text)"""
ENGLISH_G2P_NEW = """def g2p(text, pad_start_end=True, tokenized=None):
    if tokenized is None:
        tokenized = _get_tokenizer().tokenize(text)"""

JAPANESE_OLD = """model_id = 'tohoku-nlp/bert-base-japanese-v3'
tokenizer = AutoTokenizer.from_pretrained(model_id)
def g2p(norm_text):

    tokenized = tokenizer.tokenize(norm_text)"""
JAPANESE_NEW = """model_id = 'tohoku-nlp/bert-base-japanese-v3'
tokenizer = None


def _get_jp_tokenizer():
    global tokenizer
    if tokenizer is None:
        tokenizer = AutoTokenizer.from_pretrained(model_id)
    return tokenizer


def g2p(norm_text):

    tokenized = _get_jp_tokenizer().tokenize(norm_text)"""


def patch_cleaner() -> bool:
    p = MEL / "cleaner.py"
    if "_lang_mod" in p.read_text(encoding="utf-8"):
        print("[skip] cleaner.py already patched")
        return False
    p.write_text(LAZY_CLEANER, encoding="utf-8")
    print("[done] cleaner.py -> lazy language imports")
    return True


def patch_english() -> bool:
    p = MEL / "english.py"
    src = p.read_text(encoding="utf-8")
    changed = False
    if ENGLISH_TOKENIZER_OLD in src:
        src = src.replace(ENGLISH_TOKENIZER_OLD, ENGLISH_TOKENIZER_NEW)
        changed = True
    if ENGLISH_G2P_OLD in src:
        src = src.replace(ENGLISH_G2P_OLD, ENGLISH_G2P_NEW)
        changed = True
    if changed:
        p.write_text(src, encoding="utf-8")
        print("[done] english.py -> lazy tokenizer")
    else:
        print("[skip] english.py already patched")
    return changed


def patch_japanese() -> bool:
    p = MEL / "japanese.py"
    src = p.read_text(encoding="utf-8")
    if "_get_jp_tokenizer" in src:
        print("[skip] japanese.py already patched")
        return False
    if JAPANESE_OLD not in src:
        print("[warn] japanese.py pattern not found - upstream changed?")
        return False
    p.write_text(src.replace(JAPANESE_OLD, JAPANESE_NEW), encoding="utf-8")
    print("[done] japanese.py -> lazy tokenizer")
    return True


def patch_get_bert() -> bool:
    """melo/text/__init__.py: route get_bert per-language lazily."""
    p = MEL / "__init__.py"
    src = p.read_text(encoding="utf-8")
    if "def get_bert" not in src or "_bert_map" in src:
        print("[skip] text/__init__.py already patched or missing")
        return False
    old_start = src.index("def get_bert(")
    old_end = src.index("return bert", old_start) + len("return bert")
    lazy = (
        "def get_bert(norm_text, word2ph, language, device):\n"
        "    if language == \"ZH\":\n"
        "        from .chinese_bert import get_bert_feature as f\n"
        "    elif language == \"EN\":\n"
        "        from .english_bert import get_bert_feature as f\n"
        "    elif language == \"JP\":\n"
        "        from .japanese_bert import get_bert_feature as f\n"
        "    elif language == \"ZH_MIX_EN\":\n"
        "        from .chinese_mix import get_bert_feature as f\n"
        "    elif language in (\"SP\", \"ES\"):\n"
        "        from .spanish_bert import get_bert_feature as f\n"
        "    elif language == \"FR\":\n"
        "        from .french_bert import get_bert_feature as f\n"
        "    elif language == \"KR\":\n"
        "        from .korean import get_bert_feature as f\n"
        "    else:\n"
        "        raise ValueError(f\"unsupported language {language}\")\n"
        "    bert = f(norm_text, word2ph, device)\n"
        "    return bert"
    )
    p.write_text(src[:old_start] + lazy + src[old_end:], encoding="utf-8")
    print("[done] text/__init__.py -> lazy get_bert routing")
    return True


if __name__ == "__main__":
    patch_cleaner()
    patch_english()
    patch_japanese()
    patch_get_bert()
    print("MeloTTS patch complete.")
