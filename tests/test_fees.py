from datetime import date, datetime
from decimal import Decimal

import pytest

from cedikit import fees
from cedikit.fees.calculator import _Rule

D = Decimal


@pytest.mark.parametrize(
    ("network", "kind", "amount", "on", "fee", "tax"),
    [
        # Reproduce real (anonymised) messages
        ("TELECEL", "send_other_network", "40.00", date(2026, 9, 25), "0.20", "0.00"),
        ("TELECEL", "send_other_network", "25.00", date(2026, 1, 15), "0.13", "0.00"),
        ("TELECEL", "send_same_network", "100.00", date(2026, 6, 30), "0.00", "0.00"),
        ("TELECEL", "airtime", "45.00", date(2026, 9, 20), "0.00", "0.00"),
        ("MTN", "cash_out", "50.00", date(2026, 1, 1), "0.50", "0.00"),
        ("MTN", "cash_in", "430.00", date(2026, 1, 1), "0.00", "0.00"),
        ("mtn", "merchant", "51.00", date(2026, 9, 1), "0.00", "0.00"),
    ],
)
def test_matches_observed_messages(
    network: str, kind: fees.Kind, amount: str, on: date, fee: str, tax: str
) -> None:
    e = fees.estimate(network, kind, amount, on)
    assert (e.fee, e.tax) == (D(fee), D(tax))
    assert e.known and e.is_estimate
    assert e.total == D(fee) + D(tax)


def test_e_levy_2024_matches_mtn_message() -> None:
    e = fees.estimate("MTN", "send_other_network", "4000", date(2024, 5, 26))
    assert e.tax == D("40.00")
    assert e.fee is None  # 1 sample can't tell a rate from a cap
    assert not e.known and e.total is None
    assert "unknown" in str(e) and "estimate" in str(e)


def test_e_levy_periods() -> None:
    assert fees.estimate("TELECEL", "send_same_network", "100", date(2021, 1, 1)).tax == D("0.00")
    # Repealed from 2 April 2025: 1% up to and including 1 April
    assert fees.estimate("TELECEL", "send_same_network", "100", date(2025, 4, 1)).tax == D("1.00")
    repealed = fees.estimate("TELECEL", "send_same_network", "100", date(2025, 4, 2))
    assert repealed.tax == D("0.00") and "2 April 2025" in repealed.basis[1]
    # 2022: 1.5% above the first GHS100 of the day
    assert fees.estimate("TELECEL", "send_same_network", "300", date(2022, 7, 1)).tax == D("3.00")
    later = fees.estimate(
        "TELECEL", "send_same_network", "300", date(2022, 7, 1), sent_earlier_today="250"
    )
    assert later.tax == D("4.50")


@pytest.mark.parametrize(
    ("amount", "fee"),
    [("20", "0.50"), ("50", "0.50"), ("1500", "15.00"), ("2000", "20.00"), ("9000", "20.00")],
)
def test_mtn_cash_out_schedule(amount: str, fee: str) -> None:
    assert fees.estimate("MTN", "cash_out", amount, date(2026, 9, 1)).fee == D(fee)


@pytest.mark.parametrize(("amount", "fee"), [("100", "0.75"), ("1000", "7.50"), ("5000", "7.50")])
def test_mtn_same_network_send(amount: str, fee: str) -> None:
    assert fees.estimate("MTN", "send_same_network", amount, date(2026, 9, 1)).fee == D(fee)


def test_levy_does_not_apply_to_cash_out() -> None:
    e = fees.estimate("MTN", "cash_out", "1000", date(2024, 1, 1))
    assert e.tax == D("0.00") and "does not apply" in e.basis[1]


def test_dates() -> None:
    assert fees.estimate("MTN", "cash_out", "10", datetime(2026, 3, 1, 9, 0)).on == date(2026, 3, 1)
    assert fees.estimate("MTN", "cash_out", "10").on == date.today()


def test_invalid_input() -> None:
    with pytest.raises(ValueError, match="Unknown kind"):
        fees.estimate("MTN", "gift", "10")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="No fee table"):
        fees.estimate("AT", "cash_out", "10")


def test_rule_caps_and_flat_fee() -> None:
    rule = _Rule(None, D("0.01"), D("1.00"), D("5.00"), D("0.50"), "test")
    assert rule.fee(D("10")) == D("1.50")  # minimum 1.00 + flat 0.50
    assert rule.fee(D("300")) == D("3.50")
    assert rule.fee(D("10000")) == D("5.50")  # maximum 5.00 + flat
