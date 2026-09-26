"""Precise parsing, formatting and word conversion for Ghana cedi amounts.

Every monetary value is a :class:`decimal.Decimal` (or a :class:`Cedi`, which
wraps one). Floats are rejected, because they cannot represent pesewas exactly::

    >>> 0.1 + 0.2
    0.30000000000000004

Example:
    >>> from cedikit import money
    >>> money.parse("GH₵1.2k")
    Decimal('1200.00')
    >>> money.format("1200.5")
    'GH₵ 1,200.50'
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Literal, Union

from cedikit.exceptions import CediTypeError, MoneyParseError

__all__ = [
    "Cedi",
    "MoneyStyle",
    "RoundingMode",
    "format",
    "parse",
    "round_pesewas",
    "to_words",
]

MoneyStyle = Literal["symbol", "code", "compact"]
RoundingMode = Literal["half_up", "bankers"]
AmountLike = Union[str, int, Decimal, "Cedi"]

SYMBOL = "GH₵"
CODE = "GHS"
_PESEWA = Decimal("0.01")
_ROUNDING = {"half_up": ROUND_HALF_UP, "bankers": ROUND_HALF_EVEN}

_FLOAT_MESSAGE = (
    "use Decimal, int or str for money, not float - floats cannot represent "
    "pesewas exactly (0.1 + 0.2 == 0.30000000000000004)"
)

_CURRENCY = r"gh\s?s|gh\s?[₵¢c]|gh|[₵¢]"
_AMOUNT_RE = re.compile(
    rf"""
    ^(?P<neg>-)?\s*
    (?P<pre>{_CURRENCY})?\s*
    (?P<neg2>-)?\s*
    (?P<num>\d{{1,3}}(?:,\d{{3}})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)\s*
    (?P<mult>thousand|million|billion|mn|bn|k|m|b)?\s*
    (?P<post>{_CURRENCY}|cedis?|pesewas?|p)?$
    """,
    re.VERBOSE | re.IGNORECASE,
)
_MULTIPLIERS = {
    "k": Decimal(1_000),
    "thousand": Decimal(1_000),
    "m": Decimal(1_000_000),
    "mn": Decimal(1_000_000),
    "million": Decimal(1_000_000),
    "b": Decimal(1_000_000_000),
    "bn": Decimal(1_000_000_000),
    "billion": Decimal(1_000_000_000),
}


def _reject_unsafe(value: object) -> None:
    if isinstance(value, float):
        raise CediTypeError(_FLOAT_MESSAGE)
    if isinstance(value, bool):
        raise CediTypeError("use Decimal, int or str for money, not bool")


def _to_decimal(value: object) -> Decimal:
    """Convert any accepted amount type to an unrounded Decimal."""
    _reject_unsafe(value)
    if isinstance(value, Cedi):
        return value.amount
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise MoneyParseError(value, "amount must be a finite number")
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        return _parse_text(value)
    raise CediTypeError(f"expected str, int, Decimal or Cedi for money, got {type(value).__name__}")


def _parse_text(text: str) -> Decimal:
    cleaned = " ".join(text.split())
    negative_parens = cleaned.startswith("(") and cleaned.endswith(")")
    if negative_parens:
        cleaned = cleaned[1:-1].strip()

    match = _AMOUNT_RE.match(cleaned)
    if match is None:
        raise MoneyParseError(text, "unrecognised format")

    signs = [match["neg"], match["neg2"], "-" if negative_parens else None]
    if sum(s is not None for s in signs) > 1:
        raise MoneyParseError(text, "more than one negative sign")

    post = (match["post"] or "").lower()
    in_pesewas = post in ("p", "pesewa", "pesewas")
    if in_pesewas and match["pre"]:
        raise MoneyParseError(text, "mixes a cedi symbol with a pesewa amount")

    amount = Decimal(match["num"].replace(",", ""))
    if match["mult"]:
        amount *= _MULTIPLIERS[match["mult"].lower()]
    if in_pesewas:
        amount /= 100
    return -amount if any(signs) else amount


def round_pesewas(amount: AmountLike, mode: RoundingMode = "half_up") -> Decimal:
    """Round an amount to the nearest pesewa (2 decimal places).

    Args:
        amount: The amount to round.
        mode: ``"half_up"`` (0.005 -> 0.01, the everyday convention) or
            ``"bankers"`` (round half to even, which avoids bias in large sums).

    Example:
        >>> round_pesewas("2.345")
        Decimal('2.35')
        >>> round_pesewas("2.345", mode="bankers")
        Decimal('2.34')
    """
    if mode not in _ROUNDING:
        raise ValueError(f"Unknown rounding mode {mode!r}; use 'half_up' or 'bankers'")
    try:
        return _to_decimal(amount).quantize(_PESEWA, rounding=_ROUNDING[mode])
    except InvalidOperation:
        raise MoneyParseError(amount, "amount is too large") from None


def parse(value: AmountLike) -> Decimal:
    """Parse a cedi amount into a Decimal rounded to the pesewa.

    Understands currency markers (``GHS``, ``GH₵``, ``GH¢``, ``GHC``, ``₵``,
    ``cedis``), thousands separators, compact suffixes (``k``, ``m``, ``bn``),
    pesewa amounts (``50p``, ``50 pesewas``) and negatives (``-5``, ``(5)``).

    Raises:
        MoneyParseError: If the text is not a recognisable amount.
        CediTypeError: If given a float.

    Example:
        >>> parse("GHS 1,200.50")
        Decimal('1200.50')
        >>> parse("50p")
        Decimal('0.50')
        >>> parse("1200 cedis")
        Decimal('1200.00')
    """
    return round_pesewas(value)


def format(
    amount: AmountLike,
    style: MoneyStyle = "symbol",
) -> str:
    """Format a cedi amount for display.

    Args:
        amount: The amount (Decimal, int, str or Cedi - never float).
        style: ``"symbol"`` (``GH₵ 1,200.50``), ``"code"`` (``GHS 1,200.50``)
            or ``"compact"`` (``GH₵ 1.2k``).

    Example:
        >>> format("1200.5", "code")
        'GHS 1,200.50'
        >>> format("2500000", "compact")
        'GH₵ 2.5M'
    """
    value = parse(amount)
    sign = "-" if value < 0 else ""
    value = abs(value)
    if style == "symbol":
        return f"{sign}{SYMBOL} {value:,.2f}"
    if style == "code":
        return f"{sign}{CODE} {value:,.2f}"
    if style == "compact":
        return f"{sign}{SYMBOL} {_compact(value)}"
    raise ValueError(f"Unknown style {style!r}; use 'symbol', 'code' or 'compact'")


def _compact(value: Decimal) -> str:
    units = [(Decimal(1_000_000_000), "B"), (Decimal(1_000_000), "M"), (Decimal(1_000), "k")]
    for i, (size, suffix) in enumerate(units):
        if value >= size:
            scaled = (value / size).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
            # 999,950 rounds to 1000.0k - promote it to 1M instead.
            if scaled >= 1000 and i > 0:
                bigger, bigger_suffix = units[i - 1]
                scaled = (value / bigger).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
                suffix = bigger_suffix
            text = f"{scaled:,f}"
            return (text[:-2] if text.endswith(".0") else text) + suffix
    return f"{value:,.2f}"


_ONES = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen"
).split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
_SCALES = (
    (10**12, "trillion"),
    (10**9, "billion"),
    (10**6, "million"),
    (10**3, "thousand"),
)


def _below_hundred(n: int) -> str:
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    return _TENS[tens] + (f"-{_ONES[ones]}" if ones else "")


def _below_thousand(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    if not hundreds:
        return _below_hundred(rest)
    words = f"{_ONES[hundreds]} hundred"
    return f"{words} and {_below_hundred(rest)}" if rest else words


def _int_to_words(n: int) -> str:
    """British English, e.g. 1005 -> 'one thousand and five'."""
    if n == 0:
        return "zero"
    parts: list[str] = []
    for size, name in _SCALES:
        chunk, n = divmod(n, size)
        if chunk:
            parts.append(f"{_int_to_words(chunk)} {name}")
    if n:
        tail = _below_thousand(n)
        parts.append(f"and {tail}" if parts and n < 100 else tail)
    return " ".join(parts)


def to_words(amount: AmountLike) -> str:
    """Spell out a cedi amount, as written on cheques and receipts.

    Uses British English conventions ("one hundred and five").

    Example:
        >>> to_words("1200.50")
        'One thousand two hundred Ghana cedis and fifty pesewas'
        >>> to_words("1")
        'One Ghana cedi'
        >>> to_words("0.05")
        'Five pesewas'
    """
    value = parse(amount)
    negative = value < 0
    cedis, pesewas = divmod(int(abs(value) * 100), 100)
    if cedis >= 10**15:
        raise ValueError("amount is too large to convert to words")

    cedi_words = f"{_int_to_words(cedis)} Ghana cedi{'' if cedis == 1 else 's'}"
    pesewa_words = f"{_int_to_words(pesewas)} pesewa{'' if pesewas == 1 else 's'}"
    if cedis and pesewas:
        words = f"{cedi_words} and {pesewa_words}"
    elif pesewas:
        words = pesewa_words
    else:
        words = cedi_words
    if negative:
        words = f"minus {words}"
    return words[0].upper() + words[1:]


class Cedi:
    """An immutable cedi amount, always held to the pesewa.

    ``Cedi`` refuses to mix with floats, so money cannot silently pick up
    floating-point error. Arithmetic results are rounded half-up to the pesewa.

    Example:
        >>> price = Cedi("12.50")
        >>> price * 3
        Cedi('37.50')
        >>> sum([Cedi("1.10"), Cedi("2.20")])
        Cedi('3.30')
        >>> Cedi("10") + 0.5
        Traceback (most recent call last):
        ...
        cedikit.exceptions.CediTypeError: use Decimal, int or str for money, not float ...
    """

    __slots__ = ("_amount",)
    _amount: Decimal

    def __init__(self, amount: AmountLike = 0) -> None:
        object.__setattr__(self, "_amount", parse(amount))

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("Cedi is immutable")

    @property
    def amount(self) -> Decimal:
        """The amount as a Decimal with exactly two decimal places."""
        return self._amount

    @staticmethod
    def _operand(other: object) -> Decimal | None:
        """Return other as a Decimal, None if unsupported; raise for floats."""
        _reject_unsafe(other)
        if isinstance(other, Cedi):
            return other.amount
        if isinstance(other, (int, Decimal)):
            return _to_decimal(other)
        return None

    def __add__(self, other: object) -> Cedi:
        value = self._operand(other)
        if value is None:
            return NotImplemented
        return Cedi(self._amount + value)

    __radd__ = __add__

    def __sub__(self, other: object) -> Cedi:
        value = self._operand(other)
        if value is None:
            return NotImplemented
        return Cedi(self._amount - value)

    def __rsub__(self, other: object) -> Cedi:
        value = self._operand(other)
        if value is None:
            return NotImplemented
        return Cedi(value - self._amount)

    def __mul__(self, other: object) -> Cedi:
        if isinstance(other, Cedi):
            raise TypeError("cannot multiply two Cedi amounts")
        value = self._operand(other)
        if value is None:
            return NotImplemented
        return Cedi(self._amount * value)

    __rmul__ = __mul__

    def __truediv__(self, other: object) -> Cedi | Decimal:
        """Divide by a number (giving Cedi) or by another Cedi (giving a Decimal ratio)."""
        value = self._operand(other)
        if value is None:
            return NotImplemented
        if value == 0:
            raise ZeroDivisionError("division of a cedi amount by zero")
        if isinstance(other, Cedi):
            return self._amount / value
        return Cedi(self._amount / value)

    def __neg__(self) -> Cedi:
        return Cedi(-self._amount)

    def __pos__(self) -> Cedi:
        return self

    def __abs__(self) -> Cedi:
        return Cedi(abs(self._amount))

    def __bool__(self) -> bool:
        return bool(self._amount)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, float):
            return NotImplemented
        try:
            value = self._operand(other)
        except CediTypeError:
            return NotImplemented
        if value is None:
            return NotImplemented
        return self._amount == value

    def __hash__(self) -> int:
        return hash(self._amount)

    def _compare_value(self, other: object) -> Decimal:
        value = self._operand(other)
        if value is None:
            raise TypeError(f"cannot compare Cedi with {type(other).__name__}")
        return value

    def __lt__(self, other: object) -> bool:
        return self._amount < self._compare_value(other)

    def __le__(self, other: object) -> bool:
        return self._amount <= self._compare_value(other)

    def __gt__(self, other: object) -> bool:
        return self._amount > self._compare_value(other)

    def __ge__(self, other: object) -> bool:
        return self._amount >= self._compare_value(other)

    def __repr__(self) -> str:
        return f"Cedi('{self._amount}')"

    def __str__(self) -> str:
        return format(self._amount)

    def __format__(self, spec: str) -> str:
        if spec in ("", "symbol", "code", "compact"):
            return format(self._amount, spec or "symbol")  # type: ignore[arg-type]
        return self._amount.__format__(spec)

    def to_words(self) -> str:
        """Spell out this amount; see :func:`to_words`."""
        return to_words(self._amount)
