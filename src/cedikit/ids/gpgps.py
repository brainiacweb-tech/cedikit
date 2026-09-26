"""GhanaPostGPS digital address format checks.

A digital address such as ``AK-039-5028`` has three parts:

* a two-character district code: region letter + district letter or digit (``AK``, ``A2``);
* an area code of 3-5 digits (usually 3);
* a 4-digit unique address.

This checks the *format* and looks up region and district names; it cannot
confirm that an address exists. Sources are listed in ``regions.yaml``.

Example:
    >>> address = parse("ak0395028")
    >>> address.code, address.region, address.district
    ('AK-039-5028', 'Ashanti', 'Kumasi Metropolitan')
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

import yaml

from cedikit.exceptions import InvalidIdentifier

__all__ = ["DigitalAddress", "district_name", "is_valid_format", "parse", "region_name"]

# The unique code is always 4 digits, so an address typed without hyphens
# ("AK0395028") still splits correctly: everything before the last 4 is the area.
_PATTERN = re.compile(r"([A-Z])([A-Z0-9])-?(\d{3,5})-?(\d{4})")


@dataclass(frozen=True)
class _Codes:
    regions: dict[str, str]
    districts: dict[str, str]


@lru_cache(maxsize=1)
def _codes() -> _Codes:
    text = resources.files("cedikit.ids").joinpath("regions.yaml").read_text("utf-8")
    data = yaml.safe_load(text)
    return _Codes(
        regions={str(k): str(v) for k, v in data["regions"].items()},
        districts={str(k): str(v) for k, v in data["districts"].items()},
    )


@dataclass(frozen=True)
class DigitalAddress:
    region_code: str
    district_code: str
    area_code: str
    unique_code: str

    @property
    def code(self) -> str:
        """The address in standard form, e.g. ``"AK-039-5028"``."""
        return f"{self.region_code}{self.district_code}-{self.area_code}-{self.unique_code}"

    @property
    def region(self) -> str | None:
        """The region, e.g. ``"Ashanti"``; post-2019 regions share their parent's letter."""
        return region_name(self.region_code)

    @property
    def district(self) -> str | None:
        """The district for the two-character code, or None if it isn't in the table."""
        return district_name(self.region_code + self.district_code)

    def __str__(self) -> str:
        return self.code


def parse(value: str) -> DigitalAddress:
    """Split a digital address into its parts.

    Accepts upper or lower case, with or without hyphens and spaces.

    Raises:
        InvalidIdentifier: If the format is wrong or the region letter is unknown.
    """
    if not isinstance(value, str):
        raise InvalidIdentifier(value, "digital addresses must be text")
    compact = re.sub(r"\s", "", value).upper()
    match = _PATTERN.fullmatch(compact)
    if match is None:
        raise InvalidIdentifier(value, "expected a format like AK-039-5028")
    if match[1] not in _codes().regions:
        raise InvalidIdentifier(value, f"'{match[1]}' is not a GhanaPostGPS region letter")
    return DigitalAddress(match[1], match[2], match[3], match[4])


def is_valid_format(value: object) -> bool:
    """True if ``value`` looks like a GhanaPostGPS digital address (format only)."""
    try:
        parse(value)  # type: ignore[arg-type]
    except InvalidIdentifier:
        return False
    return True


def region_name(code: str) -> str | None:
    """The region for a region letter (or a whole address), e.g. ``"G"`` -> ``"Greater Accra"``."""
    return _codes().regions.get(code.strip()[:1].upper()) if code else None


def district_name(code: str) -> str | None:
    """The district for a district code (or a whole address).

    ``"GT"`` gives ``"Tema Metropolitan"``. Returns None for codes missing from
    the table (it may not list every district).
    """
    return _codes().districts.get(code.strip()[:2].upper()) if code else None
