"""One cheap OpenRouter call that only translates."""

from __future__ import annotations

import logging

import httpx

from saylo.config import (
    OPENROUTER_CHAT_URL,
    TRANSLATE_MAX_TOKENS,
    TRANSLATE_MODEL,
    TRANSLATE_REASONING,
    TRANSLATE_USD_PER_MILLION_INPUT,
    TRANSLATE_USD_PER_MILLION_OUTPUT,
)
from saylo.cost import Charge
from saylo.decide import clean_translation, translate_prompt

logger = logging.getLogger(__name__)


class Translation:
    def __init__(self, text: str, charge: Charge) -> None:
        self.text = text
        self.charge = charge


async def translate(
    http: httpx.AsyncClient,
    api_key: str,
    text: str,
    language_name: str,
) -> Translation:
    prompt = translate_prompt(language_name)
    payload: dict = {
        "model": TRANSLATE_MODEL,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text},
        ],
        "temperature": 0,
        "max_tokens": TRANSLATE_MAX_TOKENS,
    }
    if TRANSLATE_REASONING is not None:
        payload["reasoning"] = TRANSLATE_REASONING

    logger.info("translate prompt: %s", prompt)
    response = await http.post(
        OPENROUTER_CHAT_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=60,
    )
    if response.status_code >= 400:
        detail = response.text[:300]
        raise RuntimeError(f"OpenRouter {response.status_code}: {detail}")

    body = response.json()
    message = body["choices"][0]["message"]["content"]
    if not isinstance(message, str):
        raise RuntimeError("The translator did not return text.")
    translated = clean_translation(message)
    charge = _charge(body.get("usage") or {})
    logger.info(
        "translate id=%s chars=%s cost=%s tokens_in=%s tokens_out=%s",
        body.get("id"),
        len(translated),
        charge.usd,
        charge.input_tokens,
        charge.output_tokens,
    )
    return Translation(translated, charge)


def _charge(usage: dict) -> Charge:
    input_tokens = int(usage.get("prompt_tokens") or 0)
    output_tokens = int(usage.get("completion_tokens") or 0)
    if usage.get("cost") is not None:
        return Charge(float(usage["cost"]), input_tokens, output_tokens)
    estimated = (
        input_tokens * TRANSLATE_USD_PER_MILLION_INPUT
        + output_tokens * TRANSLATE_USD_PER_MILLION_OUTPUT
    ) / 1_000_000
    logger.info("translate cost estimated from token counts")
    return Charge(estimated, input_tokens, output_tokens, estimated=True)
