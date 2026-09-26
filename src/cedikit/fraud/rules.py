"""Rule-based checks for fake Mobile Money payment alerts.

Each check looks at one kind of evidence and returns zero or more
:class:`Signal` objects. A signal's ``strength`` (0-1) says how strongly that
evidence on its own points to a scam. Signals are combined with a noisy-OR::

    score = 1 - (1 - s1) * (1 - s2) * ...

so independent red flags reinforce each other, and checks that pass do not
water down one that fails. (A weighted average would: a perfect copy of a real
alert sent from a personal number would pass every wording check and score
only MEDIUM, although the sender alone proves it fake.)
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from importlib import resources
from typing import TYPE_CHECKING, Any, Literal

import yaml

from cedikit import money, phone
from cedikit.exceptions import MoneyParseError
from cedikit.ledger import expected_balance
from cedikit.sms.models import ParseResult, Transaction
from cedikit.sms.parser import Parser, _default_parser, clean

if TYPE_CHECKING:
    from cedikit.fraud.classifier import ScamClassifier

__all__ = ["ADVICE", "FraudReport", "Signal", "check", "risk_level"]

Risk = Literal["LOW", "MEDIUM", "HIGH"]

MEDIUM_FROM = 0.35
HIGH_ABOVE = 0.70
BALANCE_TOLERANCE = Decimal("0.01")

# How strongly each non-phrase check's evidence suggests a scam, on its own.
PERSONAL_SENDER = 0.85
UNKNOWN_SENDER = 0.3
UNRECOGNISED_ALERT = 0.5
UNRECOGNISED_ALERT_OFFICIAL = 0.2  # may just be a genuine format cedikit hasn't learnt
PARTIAL_MATCH = 0.25
BAD_TRANSACTION_ID = 0.4
BALANCE_MISMATCH = 0.7
DISGUISED_LETTERS = 0.5
ML_WEIGHT = 0.6  # a model's probability is scaled down: it's one signal among several

ADVICE = (
    "Before releasing goods or cash, confirm the payment in your official Mobile Money "
    "app or by checking your balance through your network's official USSD menu. "
    "Never rely on an SMS alone."
)

_ALERT_WORDS = re.compile(
    r"\b(?:cash[ -]?in|cash[ -]?out|cash|received?|reversal|sent|deposit|balance|balan|"
    r"transaction id|"
    r"payment|confirmed|transfer)\b",
    re.IGNORECASE,
)
_MONEY = re.compile(r"GHS ?\d|\b\d[\d,]*\.\d{2}\b")
_LOOSE_AMOUNT = re.compile(
    r"\b(?:for|of|received|deposit of)\s+GHS ?(\d[\d,]*(?:\.\d+)?)", re.IGNORECASE
)
_LOOSE_BALANCE = re.compile(
    r"\b(?:current )?balance(?: is)?:? (?:GHS ?)?(\d[\d,]*\.\d{2})", re.IGNORECASE
)
_LOOSE_ID = re.compile(r"\btransaction id:? ?(\d+)", re.IGNORECASE)
_INFLOW_WORDS = re.compile(r"\b(?:cash[ -]?in|received|deposit)\b", re.IGNORECASE)
_OUTFLOW_WORDS = re.compile(r"\b(?:cash[ -]?out|sent to|bought|payment made)\b", re.IGNORECASE)
_PHONE_LIKE = re.compile(r"\+?\d{9,15}")


@dataclass(frozen=True)
class Signal:
    """One piece of evidence from one check."""

    check: str
    strength: float
    reason: str


@dataclass(frozen=True)
class FraudReport:
    """The result of :func:`check`.

    Attributes:
        risk: ``"LOW"``, ``"MEDIUM"`` or ``"HIGH"``. A risk indicator, not a guarantee.
        score: Combined score from 0 to 1.
        reasons: Human-readable explanations, strongest first.
        checks: Each check that could run, mapped to True if it passed.
        signals: The raw evidence behind ``reasons``.
        parsed: The SMS parser's reading of the message.
        advice: What the user should do before trusting any alert.
    """

    risk: Risk
    score: float
    reasons: list[str]
    checks: dict[str, bool]
    signals: list[Signal] = field(default_factory=list)
    parsed: ParseResult | None = None
    advice: str = ADVICE

    def __str__(self) -> str:
        lines = [f"Risk: {self.risk} (score {self.score:.2f})"]
        if self.reasons:
            lines.append("Reasons:")
            lines.extend(f"  - {reason}" for reason in self.reasons)
        lines.append(self.advice)
        return "\n".join(lines)


def risk_level(score: float) -> Risk:
    """Map a 0-1 score to a risk level."""
    if score > HIGH_ABOVE:
        return "HIGH"
    if score >= MEDIUM_FROM:
        return "MEDIUM"
    return "LOW"


@dataclass(frozen=True)
class _Phrases:
    categories: list[tuple[str, float, str, list[re.Pattern[str]]]]
    misspellings: re.Pattern[str]
    misspelling_strength: float
    id_lengths: dict[str, int]


@lru_cache(maxsize=1)
def _phrases() -> _Phrases:
    text = resources.files("cedikit.fraud").joinpath("scam_phrases.yaml").read_text("utf-8")
    raw: dict[str, Any] = yaml.safe_load(text)
    categories = [
        (
            name,
            float(spec["strength"]),
            " ".join(str(spec["reason"]).split()),
            [re.compile(p, re.IGNORECASE) for p in spec["patterns"]],
        )
        for name, spec in raw["phrase_categories"].items()
    ]
    words = "|".join(raw["misspellings"]["words"])
    return _Phrases(
        categories=categories,
        misspellings=re.compile(rf"\b(?:{words})\b", re.IGNORECASE),
        misspelling_strength=float(raw["misspellings"]["strength"]),
        id_lengths={str(k): int(v) for k, v in raw["transaction_id_lengths"].items()},
    )


def _plain(text: str) -> str:
    """Strip accents, so "Suspéndéd" matches the same patterns as "Suspended"."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _check_disguise(cleaned: str, result: ParseResult) -> list[Signal]:
    if result.ok:
        return []
    disguised = [
        word
        for word in dict.fromkeys(re.findall(r"\w+", cleaned))
        if not word.isascii() and _plain(word).isascii()
    ]
    if not disguised:
        return []
    words = ", ".join(f"'{w}'" for w in disguised)
    return [
        Signal(
            "disguised_letters",
            DISGUISED_LETTERS,
            f"Uses accented letters to disguise words ({words}), a trick to slip past spam "
            "filters. Genuine alerts are plain text.",
        )
    ]


def _looks_like_alert(cleaned: str) -> bool:
    return bool(_MONEY.search(cleaned)) and len(set(_ALERT_WORDS.findall(cleaned.lower()))) >= 2


def _check_sender(sender: str | None, parser: Parser) -> list[Signal] | None:
    if sender is None or not sender.strip():
        return None
    if parser.is_official_sender(sender):
        return []
    official = " or ".join(parser.sender_ids) or "an official sender ID"
    if phone.is_valid(sender) or _PHONE_LIKE.fullmatch(sender.replace(" ", "")):
        shown = phone.format(sender, "international") if phone.is_valid(sender) else sender
        return [
            Signal(
                "sender",
                PERSONAL_SENDER,
                f"Sent from a personal phone number ({shown}), not an official sender ID "
                f"such as {official}. Genuine alerts never come from personal numbers.",
            )
        ]
    return [
        Signal(
            "sender",
            UNKNOWN_SENDER,
            f"Sender '{sender}' is not a known official Mobile Money sender ID ({official}).",
        )
    ]


def _check_format(cleaned: str, result: ParseResult, official: bool) -> list[Signal] | None:
    if result.transaction is not None:
        if result.transaction.needs_review:
            return [
                Signal(
                    "format",
                    PARTIAL_MATCH,
                    "Only partly matches a genuine alert format "
                    f"(confidence {result.transaction.confidence:.2f}).",
                )
            ]
        return []
    if not _looks_like_alert(cleaned):
        return None
    if official:
        return [
            Signal(
                "format",
                UNRECOGNISED_ALERT_OFFICIAL,
                "Unfamiliar alert format. It may be genuine wording that cedikit has not "
                "learnt yet, so confirm the payment in your app.",
            )
        ]
    return [
        Signal(
            "format",
            UNRECOGNISED_ALERT,
            "Looks like a Mobile Money alert but does not match any genuine message format.",
        )
    ]


def _check_spelling(cleaned: str) -> list[Signal]:
    rules = _phrases()
    found = list(dict.fromkeys(m.group(0) for m in rules.misspellings.finditer(cleaned)))
    if not found:
        return []
    words = ", ".join(f"'{w}'" for w in found)
    return [
        Signal(
            "spelling",
            rules.misspelling_strength,
            f"Contains spelling mistakes ({words}). Genuine alerts are machine-generated "
            "and don't have typos.",
        )
    ]


def _check_phrases(cleaned: str) -> list[Signal]:
    return [
        Signal("scam_phrases", strength, reason)
        for _name, strength, reason, patterns in _phrases().categories
        if any(p.search(cleaned) for p in patterns)
    ]


def _check_transaction_id(cleaned: str, result: ParseResult) -> list[Signal] | None:
    if result.ok:
        return []  # the template already enforced the genuine ID format
    match = _LOOSE_ID.search(cleaned)
    if match is None:
        return None
    lengths = _phrases().id_lengths
    if len(match[1]) in lengths.values():
        return []
    expected = " and ".join(f"{net} IDs have {n}" for net, n in lengths.items())
    return [
        Signal(
            "transaction_id",
            BAD_TRANSACTION_ID,
            f"Transaction ID {match[1]} has {len(match[1])} digits; genuine {expected}.",
        )
    ]


@dataclass(frozen=True)
class _Claim:
    amount: Decimal
    balance: Decimal
    direction: Literal["in", "out"]
    network: str | None
    fee: Decimal
    tax: Decimal


def _claim(cleaned: str, result: ParseResult) -> _Claim | None:
    """What the message claims happened, from the parser or a loose reading."""
    tx = result.transaction
    if tx is not None:
        if not tx.affects_wallet or tx.balance is None:
            return None
        return _Claim(
            tx.amount, tx.balance, tx.type.direction, tx.network, tx.fee or Decimal(0),
            tx.tax or Decimal(0),
        )  # fmt: skip
    amount, balance = _LOOSE_AMOUNT.search(cleaned), _LOOSE_BALANCE.search(cleaned)
    if amount is None or balance is None:
        return None
    if _INFLOW_WORDS.search(cleaned):
        direction: Literal["in", "out"] = "in"
    elif _OUTFLOW_WORDS.search(cleaned):
        direction = "out"
    else:
        return None
    try:
        return _Claim(
            money.parse(amount[1]), money.parse(balance[1]), direction, None,
            Decimal(0), Decimal(0),
        )  # fmt: skip
    except MoneyParseError:  # pragma: no cover - the regexes only capture valid numbers
        return None


def _check_balance(
    cleaned: str,
    result: ParseResult,
    history: Iterable[Transaction | ParseResult],
) -> list[Signal] | None:
    claim = _claim(cleaned, result)
    if claim is None:
        return None
    previous: Transaction | None = None
    for item in history:
        tx = item.transaction if isinstance(item, ParseResult) else item
        if tx is None or not tx.affects_wallet or tx.balance is None:
            continue
        if claim.network is None or tx.network == claim.network:
            previous = tx
    if previous is None or previous.balance is None:
        return None

    expected = expected_balance(
        previous.balance, claim.amount, claim.direction, claim.fee, claim.tax
    )
    if abs(expected - claim.balance) <= BALANCE_TOLERANCE:
        return []
    return [
        Signal(
            "balance",
            BALANCE_MISMATCH,
            f"Claimed balance {money.format(claim.balance, 'code')} does not follow from your "
            f"last genuine balance of {money.format(previous.balance, 'code')} "
            f"(expected {money.format(expected, 'code')}), unless you made other "
            "transactions in between.",
        )
    ]


def _check_classifier(message: str, classifier: ScamClassifier) -> list[Signal]:
    probability = classifier.probability(message)
    if probability < 0.5:
        return []
    genuine, scam = classifier.trained_on
    return [
        Signal(
            "ml_classifier",
            round(probability * ML_WEIGHT, 3),
            f"A model trained on {genuine + scam} labelled messages rates this "
            f"{probability:.0%} likely to be a scam.",
        )
    ]


def check(
    message: str,
    sender: str | None = None,
    history: Iterable[Transaction | ParseResult] = (),
    *,
    parser: Parser | None = None,
    classifier: ScamClassifier | None = None,
) -> FraudReport:
    """Assess how likely a payment SMS is to be fake.

    Args:
        message: The SMS text.
        sender: Who sent it (sender ID or phone number). Strongly recommended:
            fake alerts almost always come from personal numbers.
        history: Earlier *genuine* transactions from the same wallet, oldest
            first, used to check that the claimed balance adds up.
        parser: A custom SMS parser, if you use extra templates.
        classifier: An optional trained :class:`~cedikit.fraud.classifier.ScamClassifier`,
            added as one more signal.

    Returns:
        A :class:`FraudReport`. It is a risk indicator, not a guarantee:
        always confirm payments in the official app before releasing goods.

    Example:
        >>> report = check(
        ...     "SORRY YOU HAVE BEING BLOCKED BY TOO MANY AGENT REPORT, DO NOT TRY YOUR PIN",
        ...     sender="0241234567",
        ... )
        >>> report.risk
        'HIGH'
    """
    parser = parser or _default_parser()
    raw_cleaned = clean(message)
    cleaned = _plain(raw_cleaned)
    result = parser.parse(message, sender)
    official = sender is not None and parser.is_official_sender(sender)

    outcomes: dict[str, list[Signal] | None] = {
        "sender": _check_sender(sender, parser),
        "format": _check_format(cleaned, result, official),
        "spelling": _check_spelling(cleaned),
        "scam_phrases": _check_phrases(cleaned),
        "disguised_letters": _check_disguise(raw_cleaned, result),
        "transaction_id": _check_transaction_id(cleaned, result),
        "balance": _check_balance(cleaned, result, history),
    }
    if classifier is not None:
        outcomes["ml_classifier"] = _check_classifier(message, classifier)
    signals = sorted(
        (s for found in outcomes.values() if found for s in found),
        key=lambda s: s.strength,
        reverse=True,
    )
    remaining = 1.0
    for signal in signals:
        remaining *= 1 - signal.strength
    score = round(1 - remaining, 2)
    return FraudReport(
        risk=risk_level(score),
        score=score,
        reasons=[s.reason for s in signals],
        checks={name: not found for name, found in outcomes.items() if found is not None},
        signals=signals,
        parsed=result,
    )
