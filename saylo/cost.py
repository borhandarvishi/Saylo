"""Running cost of Jev and the translation model, saved per Telegram user."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path

from saylo.config import JEV_MODEL, TRANSLATE_MODEL, USAGE_PATH


def money(usd: float) -> str:
    return f"${usd:.8f}"


@dataclass(frozen=True)
class Charge:
    usd: float
    input_tokens: int = 0
    output_tokens: int = 0
    estimated: bool = False


@dataclass
class Spend:
    calls: int = 0
    usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_calls: int = 0

    def add(self, charge: Charge) -> None:
        self.calls += 1
        self.usd += charge.usd
        self.input_tokens += charge.input_tokens
        self.output_tokens += charge.output_tokens
        if charge.estimated:
            self.estimated_calls += 1


@dataclass
class UserSpend:
    jev: Spend
    llm: Spend

    @property
    def total_usd(self) -> float:
        return self.jev.usd + self.llm.usd


def _empty_bucket() -> dict:
    return {
        "calls": 0,
        "usd": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "estimated_calls": 0,
    }


class Ledger:
    def __init__(self, path: Path = USAGE_PATH) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._users: dict[str, dict] = {}
        self._load()

    def add(self, user_id: int, bucket: str, charge: Charge) -> UserSpend:
        if bucket not in {"jev", "llm"}:
            raise ValueError(bucket)
        with self._lock:
            user = self._users.setdefault(
                str(user_id), {"jev": _empty_bucket(), "llm": _empty_bucket()}
            )
            row = user[bucket]
            row["calls"] += 1
            row["usd"] += charge.usd
            row["input_tokens"] += charge.input_tokens
            row["output_tokens"] += charge.output_tokens
            if charge.estimated:
                row["estimated_calls"] += 1
            self._save()
            return self._read(user)

    def get(self, user_id: int) -> UserSpend:
        with self._lock:
            user = self._users.get(str(user_id))
            if user is None:
                return UserSpend(Spend(), Spend())
            return self._read(user)

    def panel(self, user_id: int) -> str:
        spend = self.get(user_id)
        lines = [
            "Cost so far",
            "",
            f"Jev ({JEV_MODEL})",
            f"  calls: {spend.jev.calls}",
            f"  input tokens: {spend.jev.input_tokens}",
            f"  cost: {money(spend.jev.usd)}",
            "",
            f"Translate ({TRANSLATE_MODEL})",
            f"  calls: {spend.llm.calls}",
            f"  input tokens: {spend.llm.input_tokens}",
            f"  output tokens: {spend.llm.output_tokens}",
            f"  cost: {money(spend.llm.usd)}",
            "",
            f"Total: {money(spend.total_usd)}",
            "",
            "Kokoro speech is local and free.",
        ]
        if spend.jev.estimated_calls or spend.llm.estimated_calls:
            lines.append("Some amounts are estimates; the API did not return a cost.")
        return "\n".join(lines)

    def _read(self, user: dict) -> UserSpend:
        return UserSpend(jev=_spend(user["jev"]), llm=_spend(user["llm"]))

    def _load(self) -> None:
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text())
        self._users = data.get("users", {})

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"users": self._users}, indent=2)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(payload)
        temporary.replace(self.path)


def _spend(row: dict) -> Spend:
    return Spend(
        calls=int(row.get("calls", 0)),
        usd=float(row.get("usd", 0.0)),
        input_tokens=int(row.get("input_tokens", 0)),
        output_tokens=int(row.get("output_tokens", 0)),
        estimated_calls=int(row.get("estimated_calls", 0)),
    )
