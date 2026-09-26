"""Ghana Card (National ID) number format checks.

Format: ``PPP-XXXXXXXXX-X``: a three-letter prefix, nine digits, then one
check digit. The prefix shows who the card was issued to:

* ``GHA``: Ghanaian citizens
* ``FGN``: foreign nationals legally resident in Ghana

The nine digits are random (they encode no personal details). The check
digit's algorithm is not published, so this confirms the *format* only, never
that a card exists or belongs to anyone. For individuals the PIN also serves
as the GRA Taxpayer Identification Number.

Example:
    >>> normalise("gha 123456789 0")
    'GHA-123456789-0'
    >>> card_type("FGN-123456789-0")
    'foreign national'
    >>> is_valid_format("GHA-12345-6")
    False
"""

from __future__ import annotations

import re
from typing import Literal

from cedikit.exceptions import InvalidIdentifier

__all__ = ["PREFIXES", "card_type", "is_valid_format", "mask", "normalise"]

PREFIXES: dict[str, Literal["citizen", "foreign national"]] = {
    "GHA": "citizen",
    "FGN": "foreign national",
}

_PATTERN = re.compile(r"([A-Z]{3})-?(\d{9})-?(\d)")


def normalise(value: str) -> str:
    """Return the number as ``PPP-XXXXXXXXX-X``, or raise InvalidIdentifier."""
    if not isinstance(value, str):
        raise InvalidIdentifier(value, "Ghana Card numbers must be text")
    compact = re.sub(r"\s", "", value).upper()
    match = _PATTERN.fullmatch(compact)
    if match is None:
        raise InvalidIdentifier(
            value, "expected GHA-XXXXXXXXX-X or FGN-XXXXXXXXX-X (9 digits and a check digit)"
        )
    if match[1] not in PREFIXES:
        raise InvalidIdentifier(
            value, f"'{match[1]}' is not a Ghana Card prefix (expected {' or '.join(PREFIXES)})"
        )
    return f"{match[1]}-{match[2]}-{match[3]}"


def is_valid_format(value: object) -> bool:
    """True if ``value`` looks like a Ghana Card number (format only)."""
    try:
        normalise(value)  # type: ignore[arg-type]
    except InvalidIdentifier:
        return False
    return True


def card_type(value: str) -> Literal["citizen", "foreign national"]:
    """Who the card was issued to, from its prefix."""
    return PREFIXES[normalise(value)[:3]]


def mask(value: str) -> str:
    """Hide the middle digits for logs, e.g. ``GHA-12*****89-0``."""
    number = normalise(value)
    digits = number[4:13]
    return f"{number[:3]}-{digits[:2]}{'*' * 5}{digits[-2:]}-{number[-1]}"
