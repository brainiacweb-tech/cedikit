"""Pydantic field types, for FastAPI and data validation.

Example::

    from pydantic import BaseModel
    from cedikit.integrations.pydantic_types import CediAmount, GhanaPhone

    class Order(BaseModel):
        customer: GhanaPhone      # "024 412 3456" -> "+233244123456"
        total: CediAmount         # "GH₵1,200.5"   -> Decimal("1200.50"); floats rejected
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any

from pydantic import AfterValidator, BeforeValidator

from cedikit import money, phone
from cedikit.exceptions import CedikitError
from cedikit.ids import ghana_card, gpgps

__all__ = ["CediAmount", "DigitalAddress", "GhanaCardNumber", "GhanaPhone"]


def _wrap(func: Any) -> Any:
    def validate(value: Any) -> Any:
        try:
            return func(value)
        except CedikitError as exc:  # re-raise as ValueError so pydantic reports it
            raise ValueError(str(exc)) from None

    return validate


GhanaPhone = Annotated[str, BeforeValidator(_wrap(phone.normalise))]
"""A Ghanaian mobile number, stored in E.164 form."""

CediAmount = Annotated[Decimal, BeforeValidator(_wrap(money.parse))]
"""A cedi amount rounded to the pesewa. Floats are rejected."""

GhanaCardNumber = Annotated[str, AfterValidator(_wrap(ghana_card.normalise))]
"""A Ghana Card number in ``GHA-XXXXXXXXX-X`` form (format check only)."""

DigitalAddress = Annotated[str, AfterValidator(_wrap(lambda v: gpgps.parse(v).code))]
"""A GhanaPostGPS address such as ``AK-039-5028`` (format check only)."""
