from decimal import Decimal
from typing import Any

import pytest

pd = pytest.importorskip("pandas")


def test_pandas_accessor() -> None:
    import cedikit.integrations.pandas_accessor  # noqa: F401

    phones = pd.Series(["024 412 3456", "12345", None, 244123456.0, float("nan")])
    assert list(phones.cedikit.normalise()) == [
        "+233244123456", None, None, "+233244123456", None,
    ]  # fmt: skip
    assert list(phones.cedikit.normalize()) == list(phones.cedikit.normalise())
    assert list(phones.cedikit.is_valid_phone()) == [True, False, False, True, False]
    assert phones.cedikit.likely_network()[0] == "MTN"
    assert phones.cedikit.mask()[0] == "024****456"
    assert phones.cedikit.format_phone()[0] == "024 412 3456"
    assert pd.Series([Decimal("244123456")]).cedikit.normalise()[0] == "+233244123456"

    amounts = pd.Series(["GHS 1,200.50", "50p", "abc", 1.5])
    assert list(amounts.cedikit.parse_money()) == [Decimal("1200.50"), Decimal("0.50"), None, None]
    assert amounts.cedikit.format_money("code")[0] == "GHS 1,200.50"


def test_pydantic_types() -> None:
    pydantic = pytest.importorskip("pydantic")
    from cedikit.integrations.pydantic_types import (
        CediAmount,
        DigitalAddress,
        GhanaCardNumber,
        GhanaPhone,
    )

    class Order(pydantic.BaseModel):  # type: ignore[misc]
        phone: GhanaPhone
        total: CediAmount
        card: GhanaCardNumber
        address: DigitalAddress

    order = Order(
        phone="024 412 3456", total="GH₵1,200.5", card="gha1234567890", address="ak0395028"
    )
    assert order.phone == "+233244123456"
    assert order.total == Decimal("1200.50")
    assert (order.card, order.address) == ("GHA-123456789-0", "AK-039-5028")
    with pytest.raises(pydantic.ValidationError, match="not float"):
        Order(phone="0244123456", total=12.5, card="GHA-123456789-0", address="AK-039-5028")
    with pytest.raises(pydantic.ValidationError, match="Invalid Ghanaian phone number"):
        Order(phone="123", total="1", card="GHA-123456789-0", address="AK-039-5028")


def test_django_validators() -> None:
    pytest.importorskip("django")
    from django.core.exceptions import ValidationError

    from cedikit.integrations.django_validators import (
        validate_cedi_amount,
        validate_digital_address,
        validate_ghana_card,
        validate_ghana_phone,
    )

    validate_ghana_phone("0244123456")
    validate_cedi_amount("GHS 5")
    validate_ghana_card("GHA-123456789-0")
    validate_digital_address("AK-039-5028")
    cases: list[tuple[Any, Any, str]] = [
        (validate_ghana_phone, "123", "invalid_phone"),
        (validate_cedi_amount, "abc", "invalid_amount"),
        (validate_ghana_card, "GHA-1", "invalid"),
        (validate_digital_address, "ZZ-1", "invalid"),
    ]
    for validator, value, code in cases:
        with pytest.raises(ValidationError) as exc:
            validator(value)
        assert exc.value.code == code


def test_wtforms_validators() -> None:
    pytest.importorskip("wtforms")
    from wtforms import Form, StringField

    class MultiDict(dict[str, str]):
        """Minimal stand-in for Flask's form data."""

        def getlist(self, key: str) -> list[str]:
            return [self[key]] if key in self else []

    from cedikit.integrations.flask_validators import (
        CediAmount,
        DigitalAddress,
        GhanaCard,
        GhanaPhone,
    )

    class PaymentForm(Form):  # type: ignore[misc]
        phone = StringField(validators=[GhanaPhone()])
        amount = StringField(validators=[CediAmount(message="Bad amount")])
        card = StringField(validators=[GhanaCard()])
        address = StringField(validators=[DigitalAddress()])

    good = PaymentForm(
        MultiDict({"phone": "0244123456", "amount": "GHS 5", "card": "", "address": "AK-039-5028"})
    )
    assert good.validate(), good.errors
    bad = PaymentForm(MultiDict({"phone": "123", "amount": "abc", "card": "x", "address": "y"}))
    assert not bad.validate()
    assert bad.errors["amount"] == ["Bad amount"]
    assert set(bad.errors) == {"phone", "amount", "card", "address"}
