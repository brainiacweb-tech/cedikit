"""Normalise, validate, format and mask Ghanaian mobile phone numbers.

Example:
    >>> from cedikit import phone
    >>> phone.normalise("024 412 3456")
    '+233244123456'
    >>> phone.format("+233244123456", "pretty")
    '024 412 3456'
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources
from typing import Any, Literal

import yaml

from cedikit.exceptions import InvalidPhoneNumber

__all__ = [
    "CleanReport",
    "CleanResult",
    "NetworkGuess",
    "PhoneStyle",
    "clean_column",
    "format",
    "is_valid",
    "likely_network",
    "mask",
    "normalise",
    "normalize",
]

PhoneStyle = Literal["e164", "local", "pretty", "international"]

_SEPARATORS = re.compile(r"[\s\-()./]")  # \s also matches non-breaking spaces


@dataclass(frozen=True)
class _PrefixData:
    version: str
    country_code: str
    national_length: int
    prefix_to_network: dict[str, str]
    display_names: dict[str, str]


@lru_cache(maxsize=1)
def _prefix_data() -> _PrefixData:
    text = resources.files("cedikit.data").joinpath("prefixes.yaml").read_text(encoding="utf-8")
    raw = yaml.safe_load(text)
    prefix_to_network: dict[str, str] = {}
    display_names: dict[str, str] = {}
    for network, info in raw["networks"].items():
        display_names[network] = info.get("display_name", network)
        for prefix in info["prefixes"]:
            prefix_to_network[str(prefix)] = network
    return _PrefixData(
        version=str(raw["version"]),
        country_code=str(raw["country_code"]),
        national_length=int(raw["national_number_length"]),
        prefix_to_network=prefix_to_network,
        display_names=display_names,
    )


@dataclass(frozen=True)
class NetworkGuess:
    """The network a number was originally assigned to.

    ``certainty`` is never stronger than ``"likely"`` because subscribers can
    keep their number when they move networks (mobile number portability).
    """

    network: str | None
    certainty: Literal["likely", "unknown"]
    note: str


def _national_number(value: object) -> str:
    """Return the 9-digit national significant number, or raise InvalidPhoneNumber."""
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise InvalidPhoneNumber(value, f"expected str or int, got {type(value).__name__}")

    data = _prefix_data()
    cc = data.country_code
    length = data.national_length

    text = _SEPARATORS.sub("", str(value).strip())
    if not text:
        raise InvalidPhoneNumber(value, "empty input")

    if text.startswith("+"):
        text = text[1:]
        if not text.startswith(cc):
            raise InvalidPhoneNumber(value, f"country code is not +{cc}")
        digits = text[len(cc) :]
    elif text.startswith("00" + cc):
        digits = text[2 + len(cc) :]
    elif text.startswith(cc) and len(text) in (len(cc) + length, len(cc) + length + 1):
        digits = text[len(cc) :]
    elif text.startswith("0") and len(text) == length + 1:
        digits = text[1:]
    else:
        digits = text

    if not digits.isdigit():
        raise InvalidPhoneNumber(value, "contains characters that are not digits")

    # Common mistake: keeping the trunk 0 after the country code (+233 024 ...).
    if len(digits) == length + 1 and digits.startswith("0"):
        digits = digits[1:]

    if len(digits) != length:
        raise InvalidPhoneNumber(
            value, f"expected {length} digits after the country code, got {len(digits)}"
        )
    if digits[:2] not in data.prefix_to_network:
        raise InvalidPhoneNumber(value, f"0{digits[:2]} is not a known Ghanaian mobile prefix")
    return digits


def normalise(value: str | int) -> str:
    """Convert a Ghanaian mobile number in any common format to E.164.

    Accepts forms such as ``0244123456``, ``+233 24 412 3456``,
    ``233244123456``, ``00233244123456`` and ``24 412 3456``.

    Args:
        value: The phone number as typed by a user.

    Returns:
        The number in E.164 format, e.g. ``'+233244123456'``.

    Raises:
        InvalidPhoneNumber: If the number cannot be normalised. The exception's
            ``reason`` attribute explains why.

    Example:
        >>> normalise("(024) 412-3456")
        '+233244123456'
    """
    return f"+{_prefix_data().country_code}{_national_number(value)}"


normalize = normalise  # US-spelling alias


def is_valid(value: object) -> bool:
    """Return True if ``value`` is a valid Ghanaian mobile number in any common format.

    Example:
        >>> is_valid("0244123456")
        True
        >>> is_valid("02441234")
        False
    """
    try:
        _national_number(value)
    except InvalidPhoneNumber:
        return False
    return True


def format(value: str | int, style: PhoneStyle = "e164") -> str:
    """Format a Ghanaian mobile number.

    Args:
        value: The phone number in any common format.
        style: One of ``"e164"`` (``+233244123456``), ``"local"`` (``0244123456``),
            ``"pretty"`` (``024 412 3456``) or ``"international"`` (``+233 24 412 3456``).

    Raises:
        InvalidPhoneNumber: If the number is invalid.
        ValueError: If ``style`` is not recognised.

    Example:
        >>> format("233244123456", "international")
        '+233 24 412 3456'
    """
    n = _national_number(value)
    cc = _prefix_data().country_code
    if style == "e164":
        return f"+{cc}{n}"
    if style == "local":
        return f"0{n}"
    if style == "pretty":
        return f"0{n[:2]} {n[2:5]} {n[5:]}"
    if style == "international":
        return f"+{cc} {n[:2]} {n[2:5]} {n[5:]}"
    raise ValueError(f"Unknown style {style!r}; use 'e164', 'local', 'pretty' or 'international'")


def likely_network(value: object) -> NetworkGuess:
    """Guess the mobile network from the number's prefix.

    The result is only ever *likely*: numbers can be ported between networks.
    Invalid numbers return ``NetworkGuess(network=None, certainty="unknown")``
    rather than raising.

    Example:
        >>> likely_network("0244123456").network
        'MTN'
    """
    try:
        n = _national_number(value)
    except InvalidPhoneNumber as exc:
        return NetworkGuess(None, "unknown", exc.reason)
    network = _prefix_data().prefix_to_network[n[:2]]
    return NetworkGuess(
        network,
        "likely",
        f"0{n[:2]} was originally assigned to {_prefix_data().display_names[network]}; "
        "the number may have been ported to another network.",
    )


def mask(value: str | int, *, visible_start: int = 3, visible_end: int = 3, char: str = "*") -> str:
    """Mask a phone number for logs and reports, e.g. ``024****456``.

    Args:
        value: A valid phone number in any common format.
        visible_start: Digits to keep at the start of the local form.
        visible_end: Digits to keep at the end.
        char: The masking character.

    Raises:
        InvalidPhoneNumber: If the number is invalid (so real data is never
            echoed back unmasked).

    Example:
        >>> mask("+233244123456")
        '024****456'
    """
    local = f"0{_national_number(value)}"
    if visible_start < 0 or visible_end < 0 or visible_start + visible_end > len(local):
        raise ValueError("visible_start and visible_end must fit within the number")
    hidden = len(local) - visible_start - visible_end
    return local[:visible_start] + char * hidden + local[len(local) - visible_end :]


@dataclass(frozen=True)
class CleanResult:
    """The outcome of cleaning one value in :func:`clean_column`."""

    original: Any
    normalised: str | None
    status: Literal["valid", "fixed", "invalid"]
    reason: str | None = None


@dataclass(frozen=True)
class CleanReport:
    """Summary of a bulk clean. ``cleaned`` lines up with the input (None for invalid)."""

    results: list[CleanResult] = field(default_factory=list)

    @property
    def cleaned(self) -> list[str | None]:
        return [r.normalised for r in self.results]

    @property
    def valid_count(self) -> int:
        return sum(r.status == "valid" for r in self.results)

    @property
    def fixed_count(self) -> int:
        return sum(r.status == "fixed" for r in self.results)

    @property
    def invalid_count(self) -> int:
        return sum(r.status == "invalid" for r in self.results)

    @property
    def invalid(self) -> list[CleanResult]:
        return [r for r in self.results if r.status == "invalid"]

    def __str__(self) -> str:
        return (
            f"{len(self.results)} numbers: {self.valid_count} valid, "
            f"{self.fixed_count} fixed, {self.invalid_count} invalid"
        )


def clean_column(values: Iterable[Any]) -> CleanReport:
    """Normalise many numbers at once, e.g. a list or a pandas Series.

    Each value is classified as ``"valid"`` (already E.164), ``"fixed"``
    (normalised from another format) or ``"invalid"`` (with a reason).
    Missing values (``None``, ``NaN``, empty strings) are reported as invalid.

    Example:
        >>> report = clean_column(["0244123456", "+233244123456", "12345"])
        >>> report.cleaned
        ['+233244123456', '+233244123456', None]
        >>> str(report)
        '3 numbers: 1 valid, 1 fixed, 1 invalid'
    """
    results: list[CleanResult] = []
    for value in values:
        if value is None or (isinstance(value, float) and value != value):
            results.append(CleanResult(value, None, "invalid", "missing value"))
            continue
        if isinstance(value, float) and value.is_integer():
            # Spreadsheets often turn 244123456 into 244123456.0
            value_for_parse: Any = int(value)
        else:
            value_for_parse = value
        try:
            e164 = normalise(value_for_parse)
        except InvalidPhoneNumber as exc:
            results.append(CleanResult(value, None, "invalid", exc.reason))
            continue
        status: Literal["valid", "fixed"] = "valid" if value == e164 else "fixed"
        results.append(CleanResult(value, e164, status))
    return CleanReport(results)
