"""Estimate Mobile Money charges and levies from dated tables."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from importlib import resources
from typing import Any, Literal, get_args

import yaml

from cedikit import money
from cedikit.money import AmountLike

__all__ = ["FeeEstimate", "Kind", "estimate"]

Kind = Literal[
    "send_same_network",
    "send_other_network",
    "cash_out",
    "cash_in",
    "receive",
    "airtime",
    "merchant",
]
_PESEWA = Decimal("0.01")


@dataclass(frozen=True)
class _Rule:
    start: date | None
    rate: Decimal
    minimum: Decimal | None
    maximum: Decimal | None
    flat: Decimal
    source: str

    def fee(self, amount: Decimal) -> Decimal:
        value = amount * self.rate
        if self.minimum is not None:
            value = max(value, self.minimum)
        if self.maximum is not None:
            value = min(value, self.maximum)
        return (value + self.flat).quantize(_PESEWA, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class _LevyPeriod:
    start: date
    end: date | None
    rate: Decimal | None
    daily_exemption: Decimal
    source: str


@dataclass(frozen=True)
class _Tables:
    charges: dict[str, dict[str, list[_Rule]]]
    levy_name: str
    levy_kinds: frozenset[str]
    levy_periods: list[_LevyPeriod]


def _dec(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _text(value: Any) -> str:
    return " ".join(str(value).split())


@lru_cache(maxsize=1)
def _tables() -> _Tables:
    folder = resources.files("cedikit.fees").joinpath("tables")
    charges: dict[str, dict[str, list[_Rule]]] = {}
    levies: dict[str, Any] = {}
    for item in folder.iterdir():
        if not item.name.endswith(".yaml"):
            continue
        data = yaml.safe_load(item.read_text(encoding="utf-8"))
        if item.name == "levies.yaml":
            levies = data
            continue
        charges[data["network"]] = {
            kind: sorted(
                (
                    _Rule(
                        start=r.get("from"),
                        rate=Decimal(str(r["rate"])),
                        minimum=_dec(r.get("min")),
                        maximum=_dec(r.get("max")),
                        flat=_dec(r.get("flat")) or Decimal(0),
                        source=_text(r["source"]),
                    )
                    for r in rules
                ),
                key=lambda rule: rule.start or date.min,
            )
            for kind, rules in (data.get("charges") or {}).items()
        }
    levy = levies["e_levy"]
    return _Tables(
        charges=charges,
        levy_name=levy["name"],
        levy_kinds=frozenset(levy["applies_to"]),
        levy_periods=[
            _LevyPeriod(
                start=p["from"],
                end=p.get("to"),
                rate=_dec(p.get("rate")),
                daily_exemption=_dec(p.get("daily_exemption")) or Decimal(0),
                source=_text(p["source"]),
            )
            for p in levy["periods"]
        ],
    )


@dataclass(frozen=True)
class FeeEstimate:
    """An *estimate* of what a transaction costs. ``None`` means unknown.

    ``basis`` explains where each number came from.
    """

    network: str
    kind: str
    amount: Decimal
    on: date
    fee: Decimal | None
    tax: Decimal | None
    basis: list[str] = field(default_factory=list)
    is_estimate: bool = True

    @property
    def known(self) -> bool:
        return self.fee is not None and self.tax is not None

    @property
    def total(self) -> Decimal | None:
        """Fee plus tax, or None if either is unknown."""
        return self.fee + self.tax if self.fee is not None and self.tax is not None else None

    def __str__(self) -> str:
        def show(v: Decimal | None) -> str:
            return money.format(v) if v is not None else "unknown"

        lines = [
            f"Estimated charges for {self.kind.replace('_', ' ')} of {money.format(self.amount)}"
            f" on {self.network} ({self.on:%d %b %Y}):",
            f"  Fee: {show(self.fee)}",
            f"  Tax: {show(self.tax)}",
            f"  Total: {show(self.total)}",
            "Basis:",
            *(f"  - {b}" for b in self.basis),
            "This is an estimate. Check your network's official tariff.",
        ]
        return "\n".join(lines)


def estimate(
    network: str,
    kind: Kind,
    amount: AmountLike,
    on: date | datetime | None = None,
    *,
    sent_earlier_today: AmountLike = 0,
) -> FeeEstimate:
    """Estimate the fee and E-Levy for a transaction.

    Args:
        network: ``"MTN"`` or ``"TELECEL"`` (case-insensitive).
        kind: What the transaction is, e.g. ``"cash_out"`` or ``"send_other_network"``.
        amount: The transaction amount.
        on: The transaction date (default: today). Historical dates use the
            rules in force then.
        sent_earlier_today: Transfers already made that day, for the E-Levy's
            daily exemption in 2022.

    Example:
        >>> e = estimate("telecel", "send_other_network", "40.00", date(2026, 9, 25))
        >>> e.fee, e.tax
        (Decimal('0.20'), Decimal('0.00'))
    """
    if kind not in get_args(Kind):
        raise ValueError(f"Unknown kind {kind!r}; use one of {', '.join(get_args(Kind))}")
    tables = _tables()
    network = network.upper()
    if network not in tables.charges:
        raise ValueError(f"No fee table for {network!r}; known: {', '.join(tables.charges)}")
    value = money.parse(amount)
    day = on.date() if isinstance(on, datetime) else on or date.today()
    basis: list[str] = []

    rules = [r for r in tables.charges[network].get(kind, []) if (r.start or date.min) <= day]
    fee: Decimal | None
    if rules:
        rule = rules[-1]
        fee = rule.fee(value)
        basis.append(f"Fee: {rule.source}")
    else:
        fee = None
        basis.append(f"Fee: no {network} rule for {kind.replace('_', ' ')} is known yet.")

    tax: Decimal | None
    if kind not in tables.levy_kinds:
        tax = Decimal("0.00")
        basis.append(f"Tax: the {tables.levy_name} does not apply to this kind of transaction.")
    else:
        period = next(
            (p for p in tables.levy_periods if p.start <= day and (p.end is None or day <= p.end)),
            None,
        )
        if period is None:
            tax = Decimal("0.00")
            basis.append(f"Tax: the {tables.levy_name} did not exist yet.")
        elif period.rate is None:
            tax = None
            basis.append(f"Tax: unknown. {period.source}")
        else:
            exempt_left = max(period.daily_exemption - money.parse(sent_earlier_today), Decimal(0))
            taxable = max(value - exempt_left, Decimal(0))
            tax = (taxable * period.rate).quantize(_PESEWA, rounding=ROUND_HALF_UP)
            basis.append(f"Tax: {period.source}")
    return FeeEstimate(network, kind, value, day, fee, tax, basis)
