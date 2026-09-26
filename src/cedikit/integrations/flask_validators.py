"""WTForms validators, for Flask-WTF forms.

Example::

    from flask_wtf import FlaskForm
    from wtforms import StringField
    from cedikit.integrations.flask_validators import CediAmount, GhanaPhone

    class PaymentForm(FlaskForm):
        phone = StringField("Phone", validators=[GhanaPhone()])
        amount = StringField("Amount", validators=[CediAmount()])
"""

from __future__ import annotations

from typing import Any

from wtforms.validators import ValidationError

from cedikit import money, phone
from cedikit.exceptions import CedikitError
from cedikit.ids import ghana_card, gpgps

__all__ = ["CediAmount", "DigitalAddress", "GhanaCard", "GhanaPhone"]


class _Validator:
    default_message = "Invalid value."

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message

    def check(self, value: Any) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def __call__(self, form: Any, field: Any) -> None:
        if field.data in (None, ""):
            return  # leave "required" to DataRequired()
        try:
            self.check(field.data)
        except CedikitError:
            raise ValidationError(self.message) from None


class GhanaPhone(_Validator):
    default_message = "Enter a valid Ghanaian mobile number."

    def check(self, value: Any) -> None:
        phone.normalise(value)


class CediAmount(_Validator):
    default_message = "Enter a valid cedi amount."

    def check(self, value: Any) -> None:
        money.parse(value)


class GhanaCard(_Validator):
    default_message = "Enter a Ghana Card number like GHA-123456789-0."

    def check(self, value: Any) -> None:
        ghana_card.normalise(value)


class DigitalAddress(_Validator):
    default_message = "Enter a GhanaPostGPS address like AK-039-5028."

    def check(self, value: Any) -> None:
        gpgps.parse(value)
