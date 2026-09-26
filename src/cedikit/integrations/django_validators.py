"""Validators for Django models and forms.

Example::

    from django.db import models
    from cedikit.integrations.django_validators import validate_ghana_phone

    class Customer(models.Model):
        phone = models.CharField(max_length=20, validators=[validate_ghana_phone])

Validators only check; use :func:`cedikit.phone.normalise` in ``clean()`` to
store numbers in one consistent format.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError

from cedikit import money, phone
from cedikit.exceptions import CedikitError
from cedikit.ids import ghana_card, gpgps

__all__ = [
    "validate_cedi_amount",
    "validate_digital_address",
    "validate_ghana_card",
    "validate_ghana_phone",
]


def _reason(exc: CedikitError) -> str:
    return str(getattr(exc, "reason", exc))


def validate_ghana_phone(value: Any) -> None:
    try:
        phone.normalise(value)
    except CedikitError as exc:
        raise ValidationError(
            "Enter a valid Ghanaian mobile number (%(reason)s).",
            code="invalid_phone",
            params={"reason": _reason(exc)},
        ) from None


def validate_cedi_amount(value: Any) -> None:
    try:
        money.parse(value)
    except CedikitError as exc:
        raise ValidationError(
            "Enter a valid cedi amount (%(reason)s).",
            code="invalid_amount",
            params={"reason": _reason(exc)},
        ) from None


def validate_ghana_card(value: Any) -> None:
    if not ghana_card.is_valid_format(value):
        raise ValidationError("Enter a Ghana Card number like GHA-123456789-0.", code="invalid")


def validate_digital_address(value: Any) -> None:
    if not gpgps.is_valid_format(value):
        raise ValidationError("Enter a GhanaPostGPS address like AK-039-5028.", code="invalid")
