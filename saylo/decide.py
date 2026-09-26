"""Pure decisions: what to ask Jev, and whether the text needs a translation."""

from __future__ import annotations

from saylo.config import MAX_INPUT_CHARS


class InputError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def clean_input(text: str) -> str:
    text = text.strip()
    if not text:
        raise InputError("Send a word or a sentence.")
    if len(text) > MAX_INPUT_CHARS:
        raise InputError(
            f"That is {len(text)} characters. The limit is {MAX_INPUT_CHARS}."
        )
    return text


def jev_prompt(language_name: str) -> str:
    return f"is this text is fully {language_name} or other language is in there?"


def jev_criteria(language_name: str) -> dict[str, None]:
    return {language_name: None, "other": None}


def translate_prompt(language_name: str) -> str:
    return f"Translate the text into {language_name}. Return only the translation."


def action_for(choice: str, jev_name: str) -> str:
    """Return 'speak' when the text is already in the selected language."""
    if choice == jev_name:
        return "speak"
    if choice == "other":
        return "translate"
    raise ValueError(f"Jev returned {choice!r}, expected {jev_name!r} or 'other'")


def clean_translation(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    if not text:
        raise ValueError("The translator returned an empty reply.")
    return text
