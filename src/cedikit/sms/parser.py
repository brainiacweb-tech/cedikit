"""Template-driven parser for Mobile Money transaction SMS."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from cedikit import money, phone
from cedikit.exceptions import InvalidPhoneNumber, MoneyParseError, TemplateError
from cedikit.sms.models import Counterparty, ParseResult, Transaction, TransactionType

__all__ = ["FIELD_PATTERNS", "GHANA_TIME", "Parser", "Template", "clean", "parse", "parse_many"]

GHANA_TIME = timezone(timedelta(0), "GMT")
"""Ghana uses GMT all year round (no daylight saving)."""

# placeholder -> (text before the group, the group's regex).
# The "GHS" before money is optional: MTN writes "TRANSACTION FEE: 0.00".
FIELD_PATTERNS: dict[str, tuple[str, str]] = {
    "amount": ("(?:GHS ?)?", r"\d[\d,]*(?:\.\d+)?"),
    "fee": ("(?:GHS ?)?", r"\d[\d,]*(?:\.\d+)?"),
    "tax": ("(?:GHS ?)?", r"\d[\d,]*(?:\.\d+)?"),
    "balance": ("(?:GHS ?)?", r"\d[\d,]*(?:\.\d+)?"),
    "available_balance": ("(?:GHS ?)?", r"\d[\d,]*(?:\.\d+)?"),
    # Letters or digits in any script (names like "JOSÉ" occur), not underscores.
    "counterparty_name": ("", r"[^\W_][\w .&'\-]*?"),
    "counterparty_phone": ("", r"\+?\d{9,13}"),
    "counterparty_network": ("", r"[A-Za-z][A-Za-z ]*?"),
    "transaction_id": ("", r"\d{6,20}"),
    "reference": ("", r".+?"),
    "date": ("", r"\d{4}-\d{2}-\d{2}"),
    "time": ("", r"\d{2}:\d{2}(?::\d{2})?"),
    "bundle": ("", r"\d+(?:\.\d+)? ?(?:GB|MB|KB)"),
}
_MONEY_FIELDS = ("amount", "fee", "tax", "balance", "available_balance")
_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")
# "GHC" may run straight into the digits ("GHC399.0"), so no \b after it.
_CURRENCY = re.compile(r"\bGH ?[₵¢]|\bGH[Cc](?![A-Za-z])|₵")
_NETWORK_ALIASES = (
    ("MTN", "MTN"),
    ("TELECEL", "TELECEL"),
    ("VODAFONE", "TELECEL"),
    ("AIRTELTIGO", "AT"),
    ("AT ", "AT"),
)


def clean(text: str) -> str:
    """Normalise whitespace and currency markers before matching.

    Example:
        >>> clean("Cash In received for GH₵ 50.00\\n from  KOFI")
        'Cash In received for GHS 50.00 from KOFI'
    """
    return " ".join(_CURRENCY.sub("GHS", text).split())


def _canonical_network(name: str) -> str:
    upper = f"{name.upper().strip()} "
    for alias, network in _NETWORK_ALIASES:
        if upper.startswith(alias) or f" {alias}" in f" {upper}":
            return network
    return upper.strip()


@dataclass(frozen=True)
class Template:
    """A compiled message template. Build these with :meth:`Parser.load_templates`."""

    name: str
    network: str
    type: TransactionType
    pattern: re.Pattern[str]
    extras: Mapping[str, re.Pattern[str]]
    required: frozenset[str]
    weight: float = 1.0
    affects_wallet: bool = True


def _expand(pattern: str, overrides: Mapping[str, str], template: str) -> tuple[str, list[str]]:
    seen: list[str] = []

    def replace(match: re.Match[str]) -> str:
        field = match[1]
        if field not in FIELD_PATTERNS:
            raise TemplateError(f"{template}: unknown placeholder {{{{{field}}}}}")
        if field in seen:
            raise TemplateError(f"{template}: placeholder {{{{{field}}}}} used twice")
        seen.append(field)
        prefix, core = FIELD_PATTERNS[field]
        return f"{prefix}(?P<{field}>{overrides.get(field, core)})"

    return _PLACEHOLDER.sub(replace, pattern), seen


def _compile(spec: Mapping[str, Any], network: str, source: str) -> Template:
    name = spec.get("name") or f"<unnamed template in {source}>"
    try:
        tx_type = TransactionType(spec["type"])
        overrides = spec.get("fields") or {}
        body, fields = _expand(" ".join(str(spec["pattern"]).split()), overrides, name)
        pattern = re.compile(body)
        extras: dict[str, re.Pattern[str]] = {}
        for field, extra in (spec.get("extras") or {}).items():
            extra_body, extra_fields = _expand(str(extra), overrides, name)
            if extra_fields != [field]:
                raise TemplateError(f"{name}: extra {field!r} must contain only {{{{{field}}}}}")
            extras[field] = re.compile(extra_body)
            fields.append(field)
    except KeyError as exc:
        raise TemplateError(f"{name} in {source}: missing key {exc}") from None
    except (ValueError, re.error) as exc:  # bad TransactionType or regex
        raise TemplateError(f"{name} in {source}: {exc}") from None

    optional = set(spec.get("optional") or ())
    if "amount" not in fields:
        raise TemplateError(f"{name}: every template needs an {{{{amount}}}}")
    if unknown := optional - set(fields):
        raise TemplateError(f"{name}: optional fields not in template: {sorted(unknown)}")
    affects_wallet = spec.get("affects_wallet", True)
    if not isinstance(affects_wallet, bool):
        raise TemplateError(f"{name}: affects_wallet must be true or false")
    return Template(
        name=name,
        network=network,
        type=tx_type,
        pattern=pattern,
        extras=extras,
        required=frozenset(fields) - optional,
        weight=float(spec.get("weight", 1.0)),
        affects_wallet=affects_wallet,
    )


class Parser:
    """Parses MoMo SMS using a set of templates.

    Most code can use the module-level :func:`parse`. Create a ``Parser`` to add
    your own templates, e.g. when a telco changes its wording before cedikit
    ships an update::

        parser = Parser(extra_template_files=["my_templates.yaml"])
    """

    def __init__(
        self,
        extra_template_files: Iterable[str | Path] = (),
        *,
        include_builtin: bool = True,
    ) -> None:
        self.templates: list[Template] = []
        self.senders: dict[str, str] = {}  # casefolded sender ID -> network
        self.sender_ids: list[str] = []  # official sender IDs as the telcos spell them
        if include_builtin:
            folder = resources.files("cedikit.sms").joinpath("templates")
            for item in sorted(folder.iterdir(), key=lambda p: p.name):
                if item.name.endswith(".yaml"):
                    self._load_text(item.read_text(encoding="utf-8"), item.name)
        for path in extra_template_files:
            self.load_templates(path)

    def load_templates(self, path: str | Path) -> None:
        """Add the templates in a YAML file (same format as the built-in ones)."""
        self._load_text(Path(path).read_text(encoding="utf-8"), str(path))

    def _load_text(self, text: str, source: str) -> None:
        data = yaml.safe_load(text) or {}
        network = data.get("network")
        if not network:
            raise TemplateError(f"{source}: missing 'network'")
        for sender in data.get("senders") or ():
            self.senders[str(sender).casefold()] = network
            self.sender_ids.append(str(sender))
        self.templates.extend(_compile(s, network, source) for s in data.get("templates") or ())

    def is_official_sender(self, sender: str) -> bool:
        """True if ``sender`` is a known official Mobile Money sender ID."""
        return sender.strip().casefold() in self.senders

    def parse(
        self,
        text: str,
        sender: str | None = None,
        received_at: datetime | None = None,
    ) -> ParseResult:
        """Parse one message. See :func:`cedikit.sms.parse`."""
        cleaned = clean(text)
        network = self.senders.get(sender.strip().casefold()) if sender else None
        # Try the sender's network first; on a tie in confidence, it wins.
        candidates = sorted(self.templates, key=lambda t: t.network != network)

        best: Transaction | None = None
        for template in candidates:
            tx = _apply(template, cleaned, text, sender, received_at)
            if tx is not None and (best is None or tx.confidence > best.confidence):
                best = tx
        if best is None:
            return ParseResult("unrecognised", None, text, sender)
        return ParseResult("parsed", best, text, sender)


def _apply(
    template: Template,
    cleaned: str,
    raw: str,
    sender: str | None,
    received_at: datetime | None,
) -> Transaction | None:
    match = template.pattern.match(cleaned)
    if match is None:
        return None
    found: dict[str, str | None] = dict(match.groupdict())
    for field, extra in template.extras.items():
        extra_match = extra.search(cleaned)
        found[field] = extra_match[field] if extra_match else None

    values: dict[str, Any] = {}
    for field in _MONEY_FIELDS:
        values[field] = _money(found.get(field))
    if values["amount"] is None:
        return None

    values["counterparty_name"] = _text(found.get("counterparty_name"))
    values["counterparty_phone"] = _phone(found.get("counterparty_phone"))
    raw_network = _text(found.get("counterparty_network"))
    values["counterparty_network"] = _canonical_network(raw_network) if raw_network else None
    values["transaction_id"] = _text(found.get("transaction_id"))
    values["reference"] = _text(found.get("reference"))
    values["bundle"] = _text(found.get("bundle"))
    timestamp = _timestamp(found.get("date"), found.get("time"))
    values["date"] = values["time"] = timestamp

    validated = sum(values.get(field) is not None for field in template.required)
    confidence = round(validated / len(template.required) * template.weight, 3)

    counterparty = None
    if values["counterparty_name"] or values["counterparty_phone"]:
        counterparty = Counterparty(
            values["counterparty_name"],
            values["counterparty_phone"],
            values["counterparty_network"],
        )
    return Transaction(
        network=template.network,
        type=template.type,
        amount=values["amount"],
        fee=values["fee"],
        tax=values["tax"],
        counterparty=counterparty,
        transaction_id=values["transaction_id"],
        reference=values["reference"],
        balance=values["balance"],
        available_balance=values["available_balance"],
        timestamp=timestamp or _in_ghana_time(received_at),
        confidence=confidence,
        template=template.name,
        sender=sender,
        raw=raw,
        affects_wallet=template.affects_wallet,
        bundle=values["bundle"],
    )


def _money(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return money.parse(value)
    except MoneyParseError:
        return None


def _phone(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return phone.normalise(value)
    except InvalidPhoneNumber:
        return None


def _text(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip(" .") or None


def _in_ghana_time(moment: datetime | None) -> datetime | None:
    """Treat a naive date-time as Ghana time, so all timestamps can be compared."""
    if moment is not None and moment.tzinfo is None:
        return moment.replace(tzinfo=GHANA_TIME)
    return moment


def _timestamp(date: str | None, time: str | None) -> datetime | None:
    if date is None or time is None:
        return None
    fmt = "%Y-%m-%d %H:%M:%S" if time.count(":") == 2 else "%Y-%m-%d %H:%M"
    try:
        return datetime.strptime(f"{date} {time}", fmt).replace(tzinfo=GHANA_TIME)
    except ValueError:
        return None


@lru_cache(maxsize=1)
def _default_parser() -> Parser:
    return Parser()


def parse(text: str, sender: str | None = None, received_at: datetime | None = None) -> ParseResult:
    """Parse a Mobile Money transaction SMS into structured data.

    Args:
        text: The message body, exactly as received.
        sender: The SMS sender ID (e.g. ``"MobileMoney"``, ``"T-CASH"``). When it
            is a known official ID, that network's templates are tried first.
        received_at: When the SMS arrived. Used as the timestamp for messages
            that carry no date of their own (e.g. MTN cash-in alerts). A time
            without a timezone is taken to be Ghana time.

    Returns:
        A :class:`ParseResult`. Check ``result.ok``; the data is in
        ``result.transaction``. Unknown formats return ``status="unrecognised"``
        instead of raising.

    Example:
        >>> result = parse(
        ...     "Cash In received for GHS 100.00 from ADOM VENTURES . Current Balance "
        ...     "GHS 120.00 Available Balance GHS 120.00. Transaction ID: 10000000001. "
        ...     "Fee charged: GHS 0.",
        ...     sender="MobileMoney",
        ... )
        >>> result.transaction.type, result.transaction.amount, result.confidence
        (<TransactionType.CASH_IN: 'CASH_IN'>, Decimal('100.00'), 1.0)
    """
    return _default_parser().parse(text, sender, received_at)


def parse_many(messages: Iterable[str], sender: str | None = None) -> list[ParseResult]:
    """Parse several messages from the same sender."""
    parser = _default_parser()
    return [parser.parse(m, sender) for m in messages]
