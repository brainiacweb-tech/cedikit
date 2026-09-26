from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml
from hypothesis import given
from hypothesis import strategies as st

from cedikit import TemplateError, sms
from cedikit.sms.parser import _canonical_network

FIXTURES = Path(__file__).parent / "fixtures" / "sample_messages"
GENUINE: list[dict[str, Any]] = yaml.safe_load((FIXTURES / "genuine.yaml").read_text("utf-8"))
BY_ID = {sample["id"]: sample for sample in GENUINE}

MONEY_FIELDS = ("amount", "fee", "tax", "balance", "available_balance")


def _actual(tx: sms.Transaction, field: str) -> object:
    if field.startswith("counterparty_"):
        assert tx.counterparty is not None
        return getattr(tx.counterparty, field.removeprefix("counterparty_"))
    if field == "timestamp":
        return tx.timestamp.isoformat() if tx.timestamp else None
    if field == "type":
        return tx.type.value
    return getattr(tx, field)


@pytest.mark.parametrize("sample", GENUINE, ids=[s["id"] for s in GENUINE])
def test_fixture_parses_to_expected_fields(sample: dict[str, Any]) -> None:
    result = sms.parse(sample["text"], sender=sample["sender"])
    assert result.ok, f"unrecognised: {sample['id']}"
    tx = result.transaction
    assert tx is not None
    for field, expected in sample["expected"].items():
        want = Decimal(expected) if field in MONEY_FIELDS else expected
        assert _actual(tx, field) == want, field
    assert tx.confidence == 1.0
    assert not tx.needs_review
    assert tx.raw == sample["text"]


@pytest.mark.parametrize("sample", GENUINE, ids=[s["id"] for s in GENUINE])
def test_fixture_parses_without_sender(sample: dict[str, Any]) -> None:
    """Scam messages come from personal numbers, so parsing must not depend on the sender."""
    result = sms.parse(sample["text"], sender="0551234567")
    assert result.ok
    assert result.transaction is not None
    assert result.transaction.template == sample["expected"]["template"]
    assert result.transaction.sender == "0551234567"


def test_unrecognised_message() -> None:
    result = sms.parse("Your data bundle expires tomorrow. Dial *138# to renew.")
    assert result.status == "unrecognised"
    assert not result.ok
    assert result.transaction is None
    assert result.confidence == 0.0


def test_received_at_fills_missing_timestamp() -> None:
    when = datetime(2026, 1, 20, 10, 4, tzinfo=sms.GHANA_TIME)
    result = sms.parse(BY_ID["mtn_cash_out"]["text"], sender="MobileMoney", received_at=when)
    assert result.transaction is not None
    assert result.transaction.timestamp == when


def test_message_timestamp_beats_received_at() -> None:
    result = sms.parse(
        BY_ID["telecel_sent_cross_network"]["text"], received_at=datetime(2000, 1, 1)
    )
    assert result.transaction is not None
    assert result.transaction.timestamp is not None
    assert result.transaction.timestamp.year == 2026


def test_optional_fields_do_not_lower_confidence() -> None:
    text = BY_ID["telecel_sent_cross_network"]["text"]
    text = text.replace(" Reference: Lunch .", "").replace(" Your E-levy charge is GHS0.00.", "")
    result = sms.parse(text, sender="T-CASH")
    assert result.transaction is not None
    assert result.transaction.reference is None
    assert result.transaction.tax is None
    assert result.confidence == 1.0


def test_unnormalisable_phone_lowers_confidence() -> None:
    text = BY_ID["telecel_sent_cross_network"]["text"].replace("0241234567", "0211234567")
    tx = sms.parse(text).transaction
    assert tx is not None
    assert tx.counterparty is not None
    assert tx.counterparty.phone is None
    assert tx.confidence == 0.875  # 7 of 8 required fields


def test_bad_date_flags_for_review() -> None:
    text = BY_ID["telecel_sent_cross_network"]["text"].replace("2026-01-15", "2026-13-45")
    tx = sms.parse(text).transaction
    assert tx is not None
    assert tx.timestamp is None
    assert tx.confidence == 0.75
    assert tx.needs_review


def test_currency_symbols_are_cleaned() -> None:
    text = (
        BY_ID["mtn_cash_out"]["text"].replace("GHS40.00", "GH₵40.00").replace("GHS0.40", "GH¢0.40")
    )
    tx = sms.parse(text).transaction
    assert tx is not None
    assert (tx.amount, tx.fee) == (Decimal("40.00"), Decimal("0.40"))


def test_clean() -> None:
    assert sms.clean("GHC 5\n\n from  GH₵ 2 ₵3") == "GHS 5 from GHS 2 GHS3"


def test_parse_many() -> None:
    results = sms.parse_many([BY_ID["mtn_cash_out"]["text"], "hello"], sender="MobileMoney")
    assert [r.ok for r in results] == [True, False]


def test_transaction_direction() -> None:
    assert sms.TransactionType.RECEIVED.direction == "in"
    assert sms.TransactionType.CASH_IN.direction == "in"
    assert sms.TransactionType.REVERSAL.direction == "in"
    assert sms.TransactionType.SENT.direction == "out"
    assert sms.TransactionType.CASH_OUT.direction == "out"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("MTN MOBILE MONEY", "MTN"),
        ("Vodafone Cash", "TELECEL"),
        ("Telecel Cash", "TELECEL"),
        ("AirtelTigo Money", "AT"),
        ("AT MONEY", "AT"),
        ("G-Money", "G-MONEY"),
    ],
)
def test_canonical_network(raw: str, expected: str) -> None:
    assert _canonical_network(raw) == expected


CUSTOM = """
network: MTN
senders: [MobileMoney]
templates:
  - name: mtn_payment_received_test
    type: RECEIVED
    weight: 0.9
    pattern: >-
      Payment received for {{amount}} from {{counterparty_name}}
      Current Balance: {{balance}}
    extras:
      transaction_id: 'Transaction ID: {{transaction_id}}'
"""


def test_custom_template_file(tmp_path: Path) -> None:
    path = tmp_path / "custom.yaml"
    path.write_text(CUSTOM, encoding="utf-8")
    parser = sms.Parser([path], include_builtin=False)
    assert [t.name for t in parser.templates] == ["mtn_payment_received_test"]

    result = parser.parse(
        "Payment received for GHS 20.00 from KOJO BOATENG Current Balance: GHS 45.00 . "
        "Transaction ID: 55512345678.",
        sender="mobilemoney",
    )
    tx = result.transaction
    assert tx is not None
    assert tx.transaction_id == "55512345678"
    assert tx.confidence == 0.9  # weight applied

    missing_id = parser.parse(
        "Payment received for GHS 20.00 from KOJO BOATENG Current Balance: GHS 45.00"
    )
    assert missing_id.transaction is not None
    assert missing_id.transaction.transaction_id is None
    assert missing_id.confidence == pytest.approx(0.9 * 3 / 4)


@pytest.mark.parametrize(
    ("yaml_text", "message"),
    [
        ("templates: []", "missing 'network'"),
        (
            "network: X\ntemplates:\n  - {name: t, type: SENT, pattern: '{{nope}}'}",
            "unknown placeholder",
        ),
        (
            "network: X\ntemplates:\n  - {name: t, type: SENT, pattern: '{{amount}} {{amount}}'}",
            "used twice",
        ),
        (
            "network: X\ntemplates:\n  - {name: t, type: SENT, pattern: '{{fee}}'}",
            "needs an {{amount}}",
        ),
        (
            "network: X\ntemplates:\n  - {name: t, type: GIFT, pattern: '{{amount}}'}",
            "GIFT",
        ),
        (
            "network: X\ntemplates:\n  - {name: t, type: SENT, pattern: '{{amount}} ('}",
            "t in",
        ),
        ("network: X\ntemplates:\n  - {name: t, type: SENT}", "missing key"),
        (
            "network: X\ntemplates:\n  - {name: t, type: SENT, pattern: '{{amount}}',"
            " optional: [fee]}",
            "optional fields not in template",
        ),
        (
            "network: X\ntemplates:\n  - {name: t, type: SENT, pattern: '{{amount}}',"
            " extras: {fee: 'x {{tax}}'}}",
            "must contain only",
        ),
        (
            "network: X\ntemplates:\n  - {name: t, type: SENT, pattern: '{{amount}}',"
            " affects_wallet: maybe}",
            "affects_wallet must be",
        ),
    ],
)
def test_bad_templates_raise(tmp_path: Path, yaml_text: str, message: str) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(yaml_text, encoding="utf-8")
    with pytest.raises(TemplateError, match=message):
        sms.Parser([path], include_builtin=False)


@given(st.text(max_size=300))
def test_parse_never_raises(text: str) -> None:
    result = sms.parse(text)
    assert result.status in ("parsed", "unrecognised")


def test_clean_ghc_directly_before_digits() -> None:
    assert sms.clean("purchased GHC399.0 Data") == "purchased GHS399.0 Data"
    assert sms.clean("GHCASH promo") == "GHCASH promo"


def test_merchant_payment_is_not_mistaken_for_network_transfer() -> None:
    text = BY_ID["mtn_sent_to_telecel"]["text"].replace("VODAFONE PUSH", "KASOA SUPERMARKET")
    assert not sms.parse(text, sender="MobileMoney").ok
