"""A ``.cedikit`` accessor for pandas Series.

Importing this module registers the accessor::

    import cedikit.integrations.pandas_accessor  # noqa: F401

    df["phone"] = df["phone"].cedikit.normalise()          # invalid -> None
    df["amount"] = df["amount"].cedikit.parse_money()      # Decimal, invalid -> None
    df["network"] = df["phone"].cedikit.likely_network()
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pandas as pd

from cedikit import money, phone
from cedikit.exceptions import CedikitError
from cedikit.phone import PhoneStyle

__all__ = ["CedikitAccessor"]


def _missing(value: Any) -> bool:
    return value is None or (isinstance(value, float) and value != value)


@pd.api.extensions.register_series_accessor("cedikit")
class CedikitAccessor:
    def __init__(self, series: pd.Series) -> None:
        self._series = series

    def _map(self, func: Any) -> pd.Series:
        def safe(value: Any) -> Any:
            if _missing(value):
                return None
            try:
                return func(value)
            except (CedikitError, ValueError, TypeError):
                return None

        # Built directly as object dtype: Series.map would turn None into NaN.
        return pd.Series([safe(v) for v in self._series], index=self._series.index, dtype=object)

    def normalise(self) -> pd.Series:
        """Phone numbers in E.164; invalid entries become None."""
        return self._map(lambda v: phone.normalise(_as_phone_input(v)))

    normalize = normalise

    def format_phone(self, style: PhoneStyle = "pretty") -> pd.Series:
        return self._map(lambda v: phone.format(_as_phone_input(v), style))

    def is_valid_phone(self) -> pd.Series:
        return self._series.map(lambda v: not _missing(v) and phone.is_valid(_as_phone_input(v)))

    def likely_network(self) -> pd.Series:
        return self._map(lambda v: phone.likely_network(_as_phone_input(v)).network)

    def mask(self) -> pd.Series:
        return self._map(lambda v: phone.mask(_as_phone_input(v)))

    def parse_money(self) -> pd.Series:
        """Exact Decimal amounts; invalid entries (and floats) become None.

        Read money columns as text (``dtype=str``) so floats never appear.
        """
        return self._map(money.parse)

    def format_money(self, style: money.MoneyStyle = "symbol") -> pd.Series:
        return self._map(lambda v: money.format(v, style))


def _as_phone_input(value: Any) -> Any:
    # Spreadsheets turn 244123456 into 244123456.0
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, Decimal):
        return int(value)
    return value
