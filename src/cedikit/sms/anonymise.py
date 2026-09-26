"""Anonymise Mobile Money SMS before sharing them or adding them to tests.

Every phone number, transaction ID, amount, date, link and (when the message
can be parsed) name and reference is replaced, while keeping what makes the
sample useful:

* wording, spacing, punctuation and line breaks are untouched;
* phone numbers keep their network prefix and format (``0...``, ``233...``);
* IDs keep their length and leading zeros;
* all amounts in a batch are scaled by the same factor and all dates shifted
  by the same number of days, so balances still add up across messages.

Always read the result before sharing it: names in messages that cannot be
parsed can't be found automatically (``needs_review`` is then True).

Example:
    >>> result = anonymise(
    ...     "Payment received for GHS 36.00 from KWESI APPIAH Current Balance: GHS 36.00 . "
    ...     "Available Balance: GHS 36.00. Reference: Rent. Transaction ID: 51234567890. "
    ...     "TRANSACTION FEE: 0.00", seed=1)
    >>> "KWESI APPIAH" in result.text, "51234567890" in result.text, result.needs_review
    (False, False, False)
"""

from __future__ import annotations

import random
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from cedikit.sms.parser import Parser, _default_parser

__all__ = ["Anonymised", "Anonymiser", "anonymise", "anonymise_many"]

_FIRST = (
    "KWAME KOFI KWABENA KWESI YAW KOJO KWADWO AMA AKOSUA ABENA ESI YAA ADWOA AFIA "
    "AKUA EFUA MANSA NANA FIIFI EKOW"
).split()
_LAST = (
    "MENSAH OWUSU ASANTE BOATENG ADJEI APPIAH DARKO OFORI ANSAH QUAYE BOAKYE "
    "DANSO FOSU TETTEH ARTHUR AMOAH ANANE BEKOE KONADU SARPONG"
).split()
_BUSINESS_WORDS = {
    "ENTERPRISE", "ENTERPRISES", "VENTURES", "VENTURE", "ELECTRICALS", "SHOP", "STORES",
    "STORE", "LOAN", "SERVICES", "CATERING", "PROVISIONS", "PHARMACY", "BAR", "SALON",
    "LIMITED", "LTD", "COMPANY", "CO", "AND", "&", "OF", "THE", "HOME", "MOBILE", "MONEY",
}  # fmt: skip
_REFERENCES = ["Rent", "Lunch", "Transport", "Stock", "Fees", "Supplies", "Gift"]

_URL = re.compile(r"(https?://[^/\s]+/)(\S+)")
_PHONE = re.compile(r"(?<!\d)(\+?233|0)([2-5]\d)(\d{7})(?!\d)")
_LONG_ID = re.compile(r"(?<!\d)\d{10,20}(?!\d)")
_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
# One pass over money, so nothing is scaled twice: an amount after a currency
# code (may be a whole number, "GHS 0"), or any other number with decimals.
_MONEY = re.compile(
    r"(?P<code>(?:GH ?[S₵¢C]|GH[sc]|₵) ?)(?P<after_code>\d[\d,]*(?:\.\d+)?)"
    r"|(?<![\d.])(?P<bare>\d[\d,]*\.\d{1,2})(?!\d)"
)


@dataclass(frozen=True)
class Anonymised:
    text: str
    needs_review: bool
    notes: list[str] = field(default_factory=list)


class Anonymiser:
    """Anonymises a batch of messages consistently (same person -> same fake name).

    Args:
        seed: Makes the output reproducible.
        scale: Factor applied to every amount (default: random between 0.5 and 1.5).
        day_shift: Days added to every date (default: random, up to about a year).
    """

    def __init__(
        self,
        seed: int | None = None,
        *,
        scale: Decimal | None = None,
        day_shift: int | None = None,
        parser: Parser | None = None,
    ) -> None:
        self.random = random.Random(seed)
        self.scale = scale if scale is not None else Decimal(self.random.randint(50, 150)) / 100
        self.day_shift = day_shift if day_shift is not None else self.random.randint(-400, -30)
        self.parser = parser or _default_parser()
        self._names: dict[str, str] = {}
        self._phones: dict[str, str] = {}
        self._ids: dict[str, str] = {}

    def __call__(self, text: str, sender: str | None = None) -> Anonymised:
        notes: list[str] = []
        result = self.parser.parse(text, sender)
        out = text
        tx = result.transaction
        if tx is not None:
            # The parser saw whitespace collapsed, so match the words across any spacing.
            if tx.counterparty and tx.counterparty.name:
                out = _words_pattern(tx.counterparty.name).sub(
                    self._fake_name(tx.counterparty.name), out
                )
            if tx.reference and not tx.reference.isdigit():
                out = _words_pattern(tx.reference).sub(self.random.choice(_REFERENCES), out)
        else:
            notes.append("Not a known format: check by hand for names and other personal text.")

        out = _URL.sub(lambda m: m[1] + re.sub(r"[A-Za-z0-9]", "x", m[2]), out)
        # IDs before phones, leaving phone-shaped numbers to the phone pass.
        out = _LONG_ID.sub(lambda m: m[0] if _PHONE.fullmatch(m[0]) else self._fake_id(m[0]), out)
        out = _PHONE.sub(self._fake_phone, out)
        out = _DATE.sub(self._shift_date, out)
        out = _MONEY.sub(
            lambda m: (
                m["code"] + self._scale(m["after_code"]) if m["code"] else self._scale(m["bare"])
            ),
            out,
        )
        return Anonymised(out, needs_review=tx is None, notes=notes)

    def _fake_name(self, name: str) -> str:
        key = " ".join(name.upper().split())
        if key not in self._names:
            fake = [w if w in _BUSINESS_WORDS else "" for w in key.split()]
            people = [i for i, w in enumerate(fake) if not w]
            for n, i in enumerate(people):
                fake[i] = self.random.choice(_FIRST if n == 0 else _LAST)
            self._names[key] = " ".join(fake)
        return self._names[key] if name.isupper() else self._names[key].title()

    def _fake_phone(self, match: re.Match[str]) -> str:
        original = match[0]
        if original not in self._phones:
            rest = "".join(str(self.random.randint(0, 9)) for _ in range(7))
            self._phones[original] = f"{match[1]}{match[2]}{rest}"
        return self._phones[original]

    def _fake_id(self, original: str) -> str:
        if original not in self._ids:
            zeros = len(original) - len(original.lstrip("0"))
            body = str(self.random.randint(1, 9)) + "".join(
                str(self.random.randint(0, 9)) for _ in range(len(original) - zeros - 1)
            )
            self._ids[original] = "0" * zeros + body
        return self._ids[original]

    def _shift_date(self, match: re.Match[str]) -> str:
        try:
            day = date(int(match[1]), int(match[2]), int(match[3]))
        except ValueError:
            return match[0]
        return (day + timedelta(days=self.day_shift)).isoformat()

    def _scale(self, number: str) -> str:
        places = len(number.split(".")[1]) if "." in number else 0
        value = Decimal(number.replace(",", "")) * self.scale
        quantum = Decimal(1).scaleb(-places)
        scaled = value.quantize(quantum, rounding=ROUND_HALF_UP)
        return f"{scaled:,f}" if "," in number else f"{scaled:f}"


def _words_pattern(text: str) -> re.Pattern[str]:
    return re.compile(r"\s+".join(re.escape(w) for w in text.split()))


def anonymise(text: str, sender: str | None = None, *, seed: int | None = None) -> Anonymised:
    """Anonymise one message. For several related messages use :func:`anonymise_many`."""
    return Anonymiser(seed)(text, sender)


def anonymise_many(
    messages: Iterable[str | tuple[str, str | None]], *, seed: int | None = None
) -> list[Anonymised]:
    """Anonymise messages with one shared scale, date shift and name mapping,
    so balances still add up and repeated people keep the same fake name."""
    anonymiser = Anonymiser(seed)
    return [anonymiser(m) if isinstance(m, str) else anonymiser(m[0], m[1]) for m in messages]
