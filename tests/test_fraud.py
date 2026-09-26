from pathlib import Path
from typing import Any

import pytest
import yaml

from cedikit import fraud, sms

FIXTURES = Path(__file__).parent / "fixtures" / "sample_messages"
GENUINE: list[dict[str, Any]] = yaml.safe_load((FIXTURES / "genuine.yaml").read_text("utf-8"))
SCAM: list[dict[str, Any]] = yaml.safe_load((FIXTURES / "scam.yaml").read_text("utf-8"))
G = {s["id"]: s for s in GENUINE}
S = {s["id"]: s for s in SCAM}


def _tx(sample_id: str) -> sms.Transaction:
    sample = G[sample_id]
    tx = sms.parse(sample["text"], sender=sample["sender"]).transaction
    assert tx is not None
    return tx


@pytest.mark.parametrize("sample", SCAM, ids=[s["id"] for s in SCAM])
def test_scam_fixtures_are_high_risk(sample: dict[str, Any]) -> None:
    report = fraud.check(sample["text"], sender=sample["sender"])
    assert report.risk == sample["expected_risk"]
    failed = sorted(name for name, passed in report.checks.items() if not passed)
    assert failed == sorted(sample["failed_checks"])


@pytest.mark.parametrize("sample", SCAM, ids=[s["id"] for s in SCAM])
def test_scam_fixtures_are_flagged_even_without_sender(sample: dict[str, Any]) -> None:
    report = fraud.check(sample["text"])
    assert report.risk == sample["risk_without_sender"]
    assert "sender" not in report.checks


@pytest.mark.parametrize("sample", GENUINE, ids=[s["id"] for s in GENUINE])
def test_genuine_fixtures_from_official_sender_are_low_risk(sample: dict[str, Any]) -> None:
    report = fraud.check(sample["text"], sender=sample["sender"])
    assert report.risk == "LOW"
    assert report.score == 0
    assert report.reasons == []
    assert all(report.checks.values())


@pytest.mark.parametrize("sample", GENUINE, ids=[s["id"] for s in GENUINE])
def test_genuine_text_from_personal_number_is_high_risk(sample: dict[str, Any]) -> None:
    """A perfect copy of a real alert is still fake if it comes from a personal number."""
    report = fraud.check(sample["text"], sender="0551234567")
    assert report.risk == "HIGH"
    assert report.checks["sender"] is False
    assert "+233 55 123 4567" in report.reasons[0]


def test_unknown_alphanumeric_sender() -> None:
    report = fraud.check(G["mtn_cash_out"]["text"], sender="MoMo-Promo")
    assert report.checks["sender"] is False
    assert report.score == 0.3
    assert report.risk == "LOW"


def test_unfamiliar_format_from_official_sender_is_only_a_caution() -> None:
    text = (
        "Your wallet has been credited with GHS 50.00 by KOJO MENSAH. "
        "Current Balance: GHS 70.00. Transaction ID: 12345678901."
    )
    report = fraud.check(text, sender="MobileMoney")
    assert report.checks["format"] is False
    assert report.risk == "LOW"
    assert "not learnt yet" in report.reasons[0]


def test_partial_match_is_flagged() -> None:
    text = G["telecel_sent_cross_network"]["text"].replace("2026-01-15", "2026-13-45")
    report = fraud.check(text, sender="T-CASH")
    assert report.checks["format"] is False
    assert report.score == 0.25


def test_wrong_length_transaction_id() -> None:
    text = "Cash In received for GHS 20.00 from X. Balance GHS 30.00. Transaction ID: 12345."
    report = fraud.check(text)
    assert report.checks["transaction_id"] is False
    assert "5 digits" in " ".join(report.reasons)


def test_ordinary_text_is_low_risk() -> None:
    report = fraud.check("Hi, are we still meeting at 4pm?")
    assert report.risk == "LOW"
    assert set(report.checks) == {"spelling", "scam_phrases", "disguised_letters"}


@pytest.mark.parametrize(
    ("text", "category_word"),
    [
        ("I sent GHS 50 to you by mistake, please send the money back", "send money back"),
        ("Wrong transfer. Please reverse it now.", "send money back"),
        ("Congratulations, you have won GHS 5000 in the MoMo promo draw", "won a prize"),
        ("Call me on this number to claim your prize", "call or message"),
        ("Enter your PIN to unlock your wallet", "your PIN"),
        ("Your account has been suspended", "blocked or suspended"),
    ],
)
def test_scam_phrases(text: str, category_word: str) -> None:
    report = fraud.check(text)
    assert report.checks["scam_phrases"] is False
    assert any(category_word in r for r in report.reasons)


def test_balance_consistency_passes_for_genuine_sequences() -> None:
    history = [_tx("mtn_cash_out")]
    report = fraud.check(G["mtn_cash_in_same_wallet"]["text"], "MobileMoney", history)
    assert report.checks["balance"] is True

    # deposit -> airtime purchase (no fee); the airtime notice is ignored.
    history = [_tx("telecel_cash_in"), _tx("telecel_airtime_received_notice")]
    report = fraud.check(G["telecel_airtime_purchase"]["text"], "T-CASH", history)
    assert report.checks["balance"] is True


def test_balance_consistency_checks_outflows_with_fees() -> None:
    history = [_tx("telecel_received_cross_network")]  # balance 205.58
    report = fraud.check(G["telecel_sent_cross_network"]["text"], "T-CASH", history)
    # 205.58 - 25.00 - 0.13 = 180.45: matches the message
    assert report.checks["balance"] is True


def test_balance_consistency_across_days_same_network() -> None:
    history = [_tx("telecel_sent_same_network")]  # balance 90.25
    report = fraud.check(G["telecel_received_same_network"]["text"], "T-CASH", history)
    assert report.checks["balance"] is True  # 90.25 + 45.00 = 135.25


def test_balance_consistency_through_loan_repayment() -> None:
    history = [_tx("mtn_received")]  # balance 36.00
    report = fraud.check(G["mtn_loan_repayment"]["text"], "MobileMoney", history)
    assert report.checks["balance"] is True  # 36.00 - 36.00 = 0.00


def test_balance_mismatch_on_fake_alert() -> None:
    history = [sms.parse(G["mtn_cash_in_same_wallet"]["text"], sender="MobileMoney")]
    report = fraud.check(S["fake_cash_in_personal_number"]["text"], history=history)
    assert report.checks["balance"] is False
    assert "GHS 322.10" in " ".join(report.reasons)
    assert "expected GHS 472.10" in " ".join(report.reasons)


def test_balance_check_skipped_without_usable_history() -> None:
    unparsed = sms.parse("hello")
    report = fraud.check(G["mtn_cash_out"]["text"], "MobileMoney", [unparsed])
    assert "balance" not in report.checks

    other_network = [_tx("telecel_cash_in")]
    report = fraud.check(G["mtn_cash_out"]["text"], "MobileMoney", other_network)
    assert "balance" not in report.checks

    # The airtime notice moves no money, so there is nothing to check.
    notice = G["telecel_airtime_received_notice"]["text"]
    report = fraud.check(notice, "T-CASH", [_tx("telecel_cash_in")])
    assert "balance" not in report.checks


def test_loose_claim_needs_a_direction() -> None:
    text = "Transaction of GHS 20.00 done. Balance GHS 30.00. Avaliable"
    report = fraud.check(text, history=[_tx("mtn_cash_out")])
    assert "balance" not in report.checks


def test_loose_outflow_claim() -> None:
    text = "Payment made for GHS 20.00 to SHOP. Current Balance: GHS 2.10. Trasaction ok"
    report = fraud.check(text, history=[_tx("mtn_cash_out")])  # 22.10 - 20.00 = 2.10
    assert report.checks["balance"] is True


def test_report_str_and_advice() -> None:
    report = fraud.check(S["fake_blocked_follow_up"]["text"], sender="+233591234567")
    text = str(report)
    assert text.startswith("Risk: HIGH (score 0.")
    assert "Reasons:" in text
    assert "official Mobile Money app" in text
    assert report.parsed is not None and not report.parsed.ok
    low = str(fraud.check("hello"))
    assert "Reasons:" not in low


@pytest.mark.parametrize(
    ("score", "risk"),
    [(0.0, "LOW"), (0.34, "LOW"), (0.35, "MEDIUM"), (0.7, "MEDIUM"), (0.71, "HIGH"), (1, "HIGH")],
)
def test_risk_level(score: float, risk: str) -> None:
    assert fraud.risk_level(score) == risk


def test_accented_letters_are_stripped_and_flagged() -> None:
    report = fraud.check("Your account is Suspéndéd")
    assert report.checks["disguised_letters"] is False
    assert report.checks["scam_phrases"] is False  # still matches "is suspended"
    assert "'Suspéndéd'" in " ".join(report.reasons)


def test_accents_in_a_parsed_genuine_alert_are_not_flagged() -> None:
    text = G["mtn_received"]["text"].replace("KWESI APPIAH", "KWESI APPIÁH")
    report = fraud.check(text, sender="MobileMoney")
    assert report.checks["disguised_letters"] is True
    assert report.risk == "LOW"


def test_non_latin_script_is_not_called_a_disguise() -> None:
    assert fraud.check("مرحبا").checks["disguised_letters"] is True
