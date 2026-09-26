"""Data models for parsed Mobile Money messages."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Literal

__all__ = ["Counterparty", "ParseResult", "Transaction", "TransactionType"]


class TransactionType(str, Enum):
    """The kind of Mobile Money transaction a message describes."""

    RECEIVED = "RECEIVED"
    SENT = "SENT"
    CASH_OUT = "CASH_OUT"
    CASH_IN = "CASH_IN"
    MERCHANT = "MERCHANT"
    AIRTIME = "AIRTIME"
    BILL = "BILL"
    REVERSAL = "REVERSAL"

    @property
    def direction(self) -> Literal["in", "out"]:
        """Whether money comes into (``"in"``) or leaves (``"out"``) the wallet."""
        return "in" if self in _INFLOWS else "out"


_INFLOWS = {TransactionType.RECEIVED, TransactionType.CASH_IN, TransactionType.REVERSAL}


@dataclass(frozen=True)
class Counterparty:
    """The other side of a transaction: a person, merchant or agent."""

    name: str | None
    phone: str | None = None  # E.164
    network: str | None = None  # e.g. "MTN" when a Telecel wallet sends to MTN


@dataclass(frozen=True)
class Transaction:
    """A single Mobile Money transaction extracted from an SMS."""

    network: str
    type: TransactionType
    amount: Decimal
    fee: Decimal | None
    tax: Decimal | None
    counterparty: Counterparty | None
    transaction_id: str | None
    reference: str | None
    balance: Decimal | None
    available_balance: Decimal | None
    timestamp: datetime | None
    confidence: float
    template: str
    sender: str | None
    raw: str
    affects_wallet: bool = True
    """False for notifications that repeat another transaction without moving money,
    e.g. "you have received airtime" after an airtime purchase. Ledgers skip these."""
    bundle: str | None = None
    """Data received in a bundle purchase, e.g. ``"214.09GB"``."""

    @property
    def needs_review(self) -> bool:
        """True when confidence is low enough that a human should check the result."""
        return self.confidence < REVIEW_THRESHOLD


REVIEW_THRESHOLD = 0.8


@dataclass(frozen=True)
class ParseResult:
    """The outcome of parsing one message.

    Unrecognised messages do not raise: ``status`` is ``"unrecognised"`` and
    ``transaction`` is None, so apps can log them for new template development.
    """

    status: Literal["parsed", "unrecognised"]
    transaction: Transaction | None
    raw: str
    sender: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "parsed"

    @property
    def confidence(self) -> float:
        return self.transaction.confidence if self.transaction else 0.0
