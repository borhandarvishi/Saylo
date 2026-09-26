"""Telegram flow.

1. English or Spanish
2. American or British, when English has more than one voice
3. Translate & speak
4. Text, up to 500 characters

Jev decides whether that text is already in the chosen language.
If it is, Kokoro reads it. If Jev says other, DeepSeek translates it first.
"""

from __future__ import annotations

import asyncio
import logging

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from saylo.config import FEATURES, LANGUAGES, VOICES, env, voices_for
from saylo.cost import Charge, Ledger, money
from saylo.decide import InputError, action_for, clean_input
from saylo.jev import Jev
from saylo.translate import translate
from saylo.tts import synthesize

logger = logging.getLogger(__name__)

_user_locks: dict[int, asyncio.Lock] = {}


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("typesafe_sdk").setLevel(logging.WARNING)

    token = env("TELEGRAM_BOT_TOKEN")
    api_key = env("OPEN_ROUTER_API_KEY", "OPENROUTER_API_KEY")

    application = (
        Application.builder()
        .token(token)
        .concurrent_updates(True)
        .post_init(_post_init(api_key))
        .post_shutdown(_post_shutdown)
        .build()
    )
    application.add_handler(CommandHandler("start", on_start))
    application.add_handler(CommandHandler("usage", on_usage))
    application.add_handler(MessageHandler(filters.COMMAND, on_unknown_command))
    application.add_handler(CallbackQueryHandler(on_button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    application.add_handler(MessageHandler(~filters.COMMAND, on_other))
    application.run_polling(drop_pending_updates=True)


def _post_init(api_key: str):
    async def post_init(application: Application) -> None:
        application.bot_data["api_key"] = api_key
        application.bot_data["http"] = httpx.AsyncClient()
        application.bot_data["ledger"] = Ledger()
        jev = Jev(api_key)
        await jev.open()
        application.bot_data["jev"] = jev
        logger.info("bot ready")

    return post_init


async def _post_shutdown(application: Application) -> None:
    jev: Jev = application.bot_data.get("jev")
    if jev is not None:
        await jev.close()
    http: httpx.AsyncClient | None = application.bot_data.get("http")
    if http is not None:
        await http.aclose()


async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    context.user_data["step"] = "language"
    await _send_screen(update.message, context.user_data)


async def on_usage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ledger: Ledger = context.application.bot_data["ledger"]
    await update.message.reply_text(ledger.panel(update.effective_user.id))


async def on_unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Use /start to begin, or /usage to see cost.")


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    state = context.user_data

    if data == "menu:usage":
        ledger: Ledger = context.application.bot_data["ledger"]
        await query.message.reply_text(ledger.panel(update.effective_user.id))
        return

    if data == "menu:start":
        state.clear()
        state["step"] = "language"
        await _edit_screen(query.message, state)
        return

    if data.startswith("lang:"):
        language = data.split(":", 1)[1]
        if language not in LANGUAGES:
            return
        state["language"] = language
        state.pop("voice", None)
        voices = voices_for(language)
        if len(voices) == 1:
            state["voice"] = voices[0]
            state["step"] = "feature"
        else:
            state["step"] = "accent"
        await _edit_screen(query.message, state)
        return

    if data.startswith("voice:"):
        voice = data.split(":", 1)[1]
        language = state.get("language")
        if voice not in voices_for(language or ""):
            await query.message.reply_text("Choose a language first.", reply_markup=_language_keyboard())
            return
        state["voice"] = voice
        state["step"] = "feature"
        await _edit_screen(query.message, state)
        return

    if data.startswith("feature:"):
        feature = data.split(":", 1)[1]
        if feature not in FEATURES or "voice" not in state:
            await query.message.reply_text("Choose a language first.", reply_markup=_language_keyboard())
            return
        state["feature"] = feature
        state["step"] = "text"
        await _edit_screen(query.message, state)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.user_data
    if state.get("step") != "text":
        state.setdefault("step", "language")
        await _send_screen(update.message, state)
        return
    if state.get("feature") != "speak":
        await update.message.reply_text("Choose Translate & speak first.")
        return

    try:
        text = clean_input(update.message.text or "")
    except InputError as exc:
        await update.message.reply_text(exc.message)
        return

    user_id = update.effective_user.id
    lock = _user_locks.setdefault(user_id, asyncio.Lock())
    if lock.locked():
        await update.message.reply_text("Still working on the previous message.")
        return

    async with lock:
        await _speak_turn(update, context, text)


async def on_other(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get("step") == "text":
        await update.message.reply_text("Send text, up to 500 characters.")


async def _speak_turn(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    state = context.user_data
    language = LANGUAGES[state["language"]]
    voice = VOICES[state["voice"]]
    user_id = update.effective_user.id
    ledger: Ledger = context.application.bot_data["ledger"]
    preview = text if logger.isEnabledFor(logging.DEBUG) else text[:80]
    logger.info("user=%s chars=%s preview=%r", user_id, len(text), preview)

    status = await update.message.reply_text("Checking language…")
    spoken = text
    translated = False
    translate_charge: Charge | None = None
    try:
        jev: Jev = context.application.bot_data["jev"]
        checked = await jev.check(text, language["jev_name"])
        ledger.add(user_id, "jev", checked.charge)
        action = action_for(checked.choice, language["jev_name"])

        if action == "translate":
            translated = True
            await status.edit_text("Translating…")
            result = await translate(
                context.application.bot_data["http"],
                context.application.bot_data["api_key"],
                text,
                language["translate_name"],
            )
            translate_charge = result.charge
            ledger.add(user_id, "llm", result.charge)
            spoken = result.text

        await status.edit_text("Reading it aloud…")
        speech = await asyncio.to_thread(
            synthesize, spoken, voice["lang_code"], voice["voice"]
        )
    except Exception as exc:
        logger.exception("turn failed user=%s", user_id)
        await status.edit_text(f"Could not finish that message.\n{type(exc).__name__}: {exc}"[:500])
        return

    audio = speech.path.read_bytes()
    try:
        caption = _caption(
            language["button"],
            voice["button"],
            checked.choice,
            checked.confidence,
            translated,
            ledger.get(user_id),
            checked.charge,
            translate_charge,
        )
        payload = InputFile(audio, filename=speech.path.name)
        if speech.kind == "voice":
            await update.message.reply_voice(voice=payload, caption=caption)
        else:
            await update.message.reply_audio(audio=payload, caption=caption)
        await status.delete()
    except Exception as exc:
        logger.exception("send failed user=%s", user_id)
        await status.edit_text(f"Could not send the voice.\n{type(exc).__name__}: {exc}"[:500])
    finally:
        speech.path.unlink(missing_ok=True)


def _caption(
    language: str,
    voice: str,
    choice: str,
    confidence: float,
    translated: bool,
    spend,
    jev_charge: Charge,
    translate_charge: Charge | None,
) -> str:
    target = language if language == voice else f"{language} ({voice})"
    if translated:
        what = f"Translated into {target}, then read aloud."
    else:
        what = f"Read aloud in {target}."
    turn = jev_charge.usd + (translate_charge.usd if translate_charge else 0.0)
    return (
        f"Jev: {choice} ({confidence:.2f})\n"
        f"{what}\n"
        f"This call {money(turn)} · total {money(spend.total_usd)}"
    )


async def _send_screen(message, state: dict) -> None:
    text, markup = _screen(state)
    await message.reply_text(text, reply_markup=markup)


async def _edit_screen(message, state: dict) -> None:
    text, markup = _screen(state)
    await message.edit_text(text, reply_markup=markup)


def _screen(state: dict) -> tuple[str, InlineKeyboardMarkup]:
    step = state.get("step", "language")
    if step == "accent":
        language = LANGUAGES[state["language"]]
        rows = [[
            (voice["button"], f"voice:{key}")
            for key, voice in VOICES.items()
            if voice["language"] == state["language"]
        ]]
        return f"{language['button']}: choose an accent.", _keyboard(rows, start=True)

    if step == "feature":
        return (
            f"{_target_label(state)}\n\nChoose what to do.",
            _keyboard([[(label, f"feature:{key}") for key, label in FEATURES.items()]], start=True),
        )

    if step == "text":
        return (
            f"{_target_label(state)}\n\n"
            "Send a word or a sentence, up to 500 characters.\n"
            "It can be in this language or any other.",
            _keyboard([], start=True),
        )

    return "Choose a language.", _keyboard([
        [(language["button"], f"lang:{key}") for key, language in LANGUAGES.items()]
    ])


def _target_label(state: dict) -> str:
    language = LANGUAGES[state["language"]]["button"]
    voice = VOICES[state["voice"]]["button"]
    if language == voice:
        return language
    return f"{language} ({voice})"


def _language_keyboard() -> InlineKeyboardMarkup:
    return _screen({"step": "language"})[1]


def _keyboard(rows: list[list[tuple[str, str]]], *, start: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(label, callback_data=data) for label, data in row]
        for row in rows
        if row
    ]
    footer = []
    if start:
        footer.append(InlineKeyboardButton("Start over", callback_data="menu:start"))
    footer.append(InlineKeyboardButton("Usage", callback_data="menu:usage"))
    buttons.append(footer)
    return InlineKeyboardMarkup(buttons)
