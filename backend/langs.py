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

# Meta MMS-TTS languages (facebook/mms-tts-<iso>) — 36M-param VITS models,
# CPU-friendly, downloaded on first use. Covers Bangla + dozens more.
MMS_ISO = {
    "ko": "kor",  # Korean via MMS (melo-KR needs a fragile mecab-ko chain)
    "bn": "ben", "hi": "hin", "ar": "ara", "de": "deu", "pt": "por",
    "ru": "rus", "it": "ita", "tr": "tur", "vi": "vie", "id": "ind",
    "nl": "nld", "pl": "pol", "ur": "urd", "ta": "tam", "te": "tel",
    "mr": "mar", "gu": "guj", "kn": "kan", "pa": "pan", "ne": "nep",
    "as": "asm", "or": "ory", "si": "sin", "sw": "swh", "th": "tha",
    "fil": "fil",
}

# short natural calibration sentences used to build preset voices
SAMPLE_SENTENCES = {
    "en": "This is my voice, and every word you hear is generated right here on this machine.",
    "es": "Esta es mi voz, y cada palabra que escuchas se genera aquí mismo.",
    "fr": "Voici ma voix, et chaque mot que vous entendez est généré ici même.",
    "zh": "这是我的声音，你听到的每一个字都是在这里生成的。",
    "ja": "これは私の声です。聞こえるすべての言葉は、この場所で生まれています。",
    "ko": "이것은 제 목소리입니다. 들리는 모든 단어는 바로 여기서 만들어집니다.",
    "bn": "এটি আমার কণ্ঠস্বর, আপনি যা শুনছেন তা এই মেশিনেই তৈরি।",
    "hi": "यह मेरी आवाज़ है, और आप जो भी सुन रहे हैं वह यहीं बना है।",
    "ar": "هذا صوتي، وكل كلمة تسمعها تولد هنا.",
    "de": "Das ist meine Stimme, und jedes Wort entsteht hier auf diesem Gerät.",
    "pt": "Esta é a minha voz, e cada palavra que você ouve nasce aqui.",
    "ru": "Это мой голос, и каждое слово рождается прямо здесь.",
    "it": "Questa è la mia voce, e ogni parola che senti nasce qui.",
    "tr": "Bu benim sesim ve duyduğunuz her kelime burada doğuyor.",
    "vi": "Đây là giọng nói của tôi, mọi từ bạn nghe đều được tạo ra tại đây.",
    "id": "Ini suara saya, dan setiap kata yang Anda dengar lahir di sini.",
    "nl": "Dit is mijn stem, en elk woord dat u hoort ontstaat hier.",
    "pl": "To jest mój głos, i każde słowo, które słyszysz, rodzi się tutaj.",
    "hi2": "यह आवाज़ आपके अपने कंप्यूटर पर बनी है।",
}


def is_mms(lang: str) -> bool:
    return (lang or "").lower() in MMS_ISO


def all_lang_list() -> dict:
    """{code: label} for UI dropdowns — melo + mms, sorted sensibly."""
    out = {k: v["label"] for k, v in LANGS.items()}
    for code in MMS_ISO:
        if code not in out:
            out[code] = LANG_LABELS_EXTRA.get(code, code)
    return out


LANG_LABELS_EXTRA = {
    "bn": "বাংলা (Bangla)", "hi": "हिन्दी", "ar": "العربية", "de": "Deutsch",
    "pt": "Português", "ru": "Русский", "it": "Italiano", "tr": "Türkçe",
    "vi": "Tiếng Việt", "id": "Bahasa Indonesia", "nl": "Nederlands",
    "pl": "Polski", "ur": "اردو", "ta": "தமிழ்", "te": "తెలుగు",
    "mr": "मराठी", "gu": "ગુજરાતી", "kn": "ಕನ್ನಡ", "pa": "ਪੰਜਾਬੀ",
    "ne": "नेपाली", "as": "অসমীয়া", "or": "ଓଡ଼ିଆ", "si": "සිංහල",
    "sw": "Kiswahili", "th": "ไทย", "fil": "Filipino",
}


def get(lang: str) -> dict:
    return LANGS.get((lang or DEFAULT_LANG).lower(), LANGS[DEFAULT_LANG])


def ses_key(lang: str, accent: str | None) -> str:
    L = get(lang)
    accs = L["accents"]
    if accent in accs:
        return L["ses"][accent]
    first = next(iter(accs))
    return L["ses"][first]
