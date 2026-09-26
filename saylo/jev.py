"""One Jev call: is the text fully in the selected language, or not?"""

from __future__ import annotations

import json
import logging

from typesafe_sdk import AsyncTypeSafeClient, Choice

from saylo.config import (
    JEV_BASE_URL,
    JEV_MODEL,
    JEV_USD_PER_MILLION_INPUT,
)
from saylo.cost import Charge
from saylo.decide import jev_criteria, jev_prompt

logger = logging.getLogger(__name__)


class LanguageCheck:
    def __init__(self, choice: str, confidence: float, charge: Charge) -> None:
        self.choice = choice
        self.confidence = confidence
        self.charge = charge


class Jev:
    def __init__(self, api_key: str) -> None:
        self._client = AsyncTypeSafeClient(
            api_key=api_key,
            base_url=JEV_BASE_URL,
            model=JEV_MODEL,
            timeout=30,
        )

    async def open(self) -> None:
        await self._client.__aenter__()

    async def close(self) -> None:
        await self._client.__aexit__(None, None, None)

    async def check(self, text: str, jev_name: str) -> LanguageCheck:
        prompt = jev_prompt(jev_name)
        logger.info("jev prompt: %s", prompt)
        response = await self._client.system_one(
            state=text,
            questions={
                "language": Choice(
                    instructions=prompt,
                    criteria=jev_criteria(jev_name),
                )
            },
        )
        answer = response.choices["language"]
        charge = _charge(response)
        logger.info(
            "jev choice=%s confidence=%.3f probabilities=%s cost=%s tokens_in=%s",
            answer.choice,
            answer.confidence,
            dict(answer.probabilities),
            charge.usd,
            charge.input_tokens,
        )
        return LanguageCheck(answer.choice, answer.confidence, charge)


def _charge(response) -> Charge:
    usage = response.usage
    input_tokens = int(usage.input_tokens or 0)
    output_tokens = int(usage.output_tokens or 0)
    billed = _openrouter_cost(response)
    if billed is not None:
        return Charge(billed, input_tokens, output_tokens, estimated=False)
    estimated = input_tokens * JEV_USD_PER_MILLION_INPUT / 1_000_000
    logger.info("jev cost estimated from input tokens")
    return Charge(estimated, input_tokens, output_tokens, estimated=True)


def _openrouter_cost(response) -> float | None:
    raw = getattr(response, "raw_http_response", None)
    if raw is None:
        return None
    try:
        body = json.loads(raw.content)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    usage = body.get("usage") if isinstance(body, dict) else None
    if not isinstance(usage, dict) or usage.get("cost") is None:
        return None
    return float(usage["cost"])
