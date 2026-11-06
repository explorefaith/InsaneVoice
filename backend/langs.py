"""InsaneVoice — language registry.

TTS languages come from the local MeloTTS family (free, CPU, MIT).
Voice changer (tone transfer) works on audio of ANY language — the
converter doesn't care what is being said, only how it sounds.
"""

LANGS = {
    "en": {
        "label": "English",
        "melo": "EN",
        "accents": {"en-us": "American", "en-br": "British"},
        "ses": {"en-us": "en-us", "en-br": "en-br"},
        "wpm": 150,
        "stt": "en-us",
    },
    "es": {
        "label": "Español",
        "melo": "ES",
        "accents": {"default": "Default"},
        "ses": {"default": "es"},
        "wpm": 155,
        "stt": "es",
    },
    "fr": {
        "label": "Français",
        "melo": "FR",
        "accents": {"default": "Default"},
        "ses": {"default": "fr"},
        "wpm": 150,
        "stt": "fr",
    },
    "zh": {
        "label": "中文",
        "melo": "ZH",
        "accents": {"default": "Default"},
        "ses": {"default": "zh"},
        "wpm": 220,
        "stt": "zh-cn",
    },
    "ja": {
        "label": "日本語",
        "melo": "JP",
        "accents": {"default": "Default"},
        "ses": {"default": "jp"},
        "wpm": 300,
        "stt": "ja",
    },
    "ko": {
        "label": "한국어",
        "melo": "KR",
        "accents": {"default": "Default"},
        "ses": {"default": "kr"},
        "wpm": 250,
        "stt": "ko",
    },
}

DEFAULT_LANG = "en"


def get(lang: str) -> dict:
    return LANGS.get((lang or DEFAULT_LANG).lower(), LANGS[DEFAULT_LANG])


def ses_key(lang: str, accent: str | None) -> str:
    L = get(lang)
    accs = L["accents"]
    if accent in accs:
        return L["ses"][accent]
    first = next(iter(accs))
    return L["ses"][first]
