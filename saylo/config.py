"""Every knob lives here. Change a voice, a model, or a limit in this file only."""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent.parent
USAGE_PATH = ROOT / "data" / "usage.json"

MAX_INPUT_CHARS = 500

# Jev is called through OpenRouter, same shape as sample_jev_request_temp.py.
JEV_MODEL = "typesafe/jev-1.13"
JEV_BASE_URL = "https://openrouter.ai/api"
# Used only when OpenRouter does not return usage.cost. Output tokens are free.
JEV_USD_PER_MILLION_INPUT = 0.042

TRANSLATE_MODEL = "deepseek/deepseek-v4.1-flash"
OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
TRANSLATE_MAX_TOKENS = 800
# Omit reasoning spend on a one-line translation. Set to None to drop the field.
TRANSLATE_REASONING = {"effort": "none"}
# Fallback prices if the response has token counts but no cost.
TRANSLATE_USD_PER_MILLION_INPUT = 0.04
TRANSLATE_USD_PER_MILLION_OUTPUT = 0.49

# Kokoro writes 24 kHz audio. https://github.com/hexgrad/kokoro
TTS_SAMPLE_RATE = 24_000
TTS_SPEED = 1.0

# jev_name is the label Jev must choose. translate_name is what we ask the LLM for.
LANGUAGES: dict[str, dict[str, str]] = {
    "en": {
        "button": "English",
        "jev_name": "english",
        "translate_name": "English",
    },
    "es": {
        "button": "Spanish",
        "jev_name": "spanish",
        "translate_name": "Spanish",
    },
}

# One Kokoro voice per accent. lang_code must match the voice prefix.
# American 'a', British 'b', Spanish 'e'.
VOICES: dict[str, dict[str, str]] = {
    "en-us": {
        "language": "en",
        "button": "American",
        "lang_code": "a",
        "voice": "af_heart",
    },
    "en-gb": {
        "language": "en",
        "button": "British",
        "lang_code": "b",
        "voice": "bf_emma",
    },
    "es": {
        "language": "es",
        "button": "Spanish",
        "lang_code": "e",
        "voice": "ef_dora",
    },
}

# The only feature today. Add another entry here, then handle it in bot.py.
FEATURES: dict[str, str] = {
    "speak": "Translate & speak",
}


def env(name: str, *aliases: str) -> str:
    for key in (name, *aliases):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    joined = ", ".join((name, *aliases))
    raise SystemExit(f"Missing environment variable: {joined}")


def voices_for(language: str) -> list[str]:
    return [key for key, voice in VOICES.items() if voice["language"] == language]
