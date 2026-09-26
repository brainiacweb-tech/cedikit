import csv
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from cedikit import __version__
from cedikit.cli import app

runner = CliRunner()
Samples = dict[str, dict[str, Any]]


def run(*args: str, input: str | None = None) -> Any:
    return runner.invoke(app, list(args), input=input)


def test_version() -> None:
    result = run("--version")
    assert result.exit_code == 0 and __version__ in result.output


def test_phone_clean(tmp_path: Path) -> None:
    src = tmp_path / "contacts.csv"
    bad = [f"12{i}" for i in range(11)]
    with src.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["name", "phone"])
        writer.writerows([["Ama", "024 412 3456"], ["Kofi", "+233501234567"]])
        writer.writerows([["x", b] for b in bad])
    result = run("phone", "clean", str(src), "--style", "pretty")
    assert result.exit_code == 0, result.output
    assert "13 numbers: 1 valid, 1 fixed, 11 invalid" in result.output
    assert "and 1 more" in result.output
    rows = list(csv.DictReader((tmp_path / "contacts_cleaned.csv").open(encoding="utf-8")))
    assert rows[0]["phone"] == "024 412 3456" and rows[0]["phone_status"] == "fixed"
    assert rows[2]["phone_status"] == "invalid" and rows[2]["phone_note"]

    missing = run("phone", "clean", str(src), "--column", "tel")
    assert missing.exit_code == 1 and "No column 'tel'" in missing.output


def test_phone_check() -> None:
    ok = run("phone", "check", "0244123456")
    assert ok.exit_code == 0 and "+233 24 412 3456" in ok.output and "MTN" in ok.output
    bad = run("phone", "check", "12345")
    assert bad.exit_code == 1


def test_money_commands() -> None:
    assert run("money", "parse", "GH₵1.2k").output.strip() == "1200.00"
    assert "Ghana cedis and fifty pesewas" in run("money", "words", "1200.50").output
    assert run("money", "parse", "abc").exit_code == 1
    assert run("money", "words", "1000000000000000").exit_code == 1


def _write_inbox(path: Path, genuine: Samples, extra: str = "") -> Path:
    ids = ["mtn_cash_out", "mtn_cash_in_same_wallet", "mtn_received", "mtn_loan_repayment"]
    path.write_text(
        "\n\n".join(genuine[i]["text"] for i in ids) + "\n\nhello there\n\n" + extra,
        encoding="utf-8",
    )
    return path


def test_sms_parse_and_export(tmp_path: Path, genuine: Samples) -> None:
    inbox = _write_inbox(
        tmp_path / "inbox.txt", genuine, genuine["telecel_airtime_received_notice"]["text"]
    )
    result = run("sms", "parse", str(inbox), "--sender", "MobileMoney", "--export", "xlsx")
    assert result.exit_code == 0, result.output
    assert "4 transactions" in result.output
    assert "1 messages were not recognised" in result.output
    assert "1 notices" in result.output
    assert "Balance gap" in result.output  # fixtures come from different wallets
    assert (tmp_path / "inbox_ledger.xlsx").exists()

    out = tmp_path / "ledger.json"
    assert run("sms", "parse", str(inbox), "--output", str(out)).exit_code == 0
    assert out.exists()
    assert run("sms", "parse", str(inbox), "--output", str(tmp_path / "x.pdf")).exit_code == 1


def test_sms_parse_csv_input(tmp_path: Path, genuine: Samples) -> None:
    src = tmp_path / "messages.csv"
    with src.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["text"])
        writer.writerow([genuine["mtn_cash_out"]["text"]])
    result = run("sms", "parse", str(src))
    assert result.exit_code == 0 and "1 transactions" in result.output


def test_sms_anonymise(tmp_path: Path, genuine: Samples) -> None:
    inbox = _write_inbox(tmp_path / "inbox.txt", genuine)
    result = run("sms", "anonymise", str(inbox), "--seed", "3")
    assert result.exit_code == 0
    assert "ADOM ELECTRICALS" not in result.output
    assert "CHECK BY HAND" in result.output  # the "hello there" message


def test_fraud_check(scam: Samples) -> None:
    sample = scam["fake_blocked_follow_up"]
    result = run("fraud", "check", sample["text"], "--sender", sample["sender"])
    assert result.exit_code == 0 and "Risk: HIGH" in result.output
    assert "Tip: pass --sender" not in result.output
    from_stdin = run("fraud", "check", "-", input=sample["text"])
    assert "Risk: HIGH" in from_stdin.output and "Tip: pass --sender" in from_stdin.output


def test_fees_estimate() -> None:
    result = run("fees", "estimate", "telecel", "send_other_network", "40", "--on", "2026-09-25")
    assert result.exit_code == 0 and "GH₵ 0.20" in result.output
    assert run("fees", "estimate", "MTN", "cash_out", "10", "--on", "yesterday").exit_code == 1


@pytest.mark.parametrize(
    ("value", "expected", "code"),
    [
        ("gha1234567890", "GHA-123456789-0", 0),
        ("ak0395028", "AK-039-5028 (Kumasi Metropolitan, Ashanti)", 0),
        ("fgn9876543215", "FGN-987654321-5 (foreign national)", 0),
        ("hello", "neither", 1),
    ],
)
def test_ids_check(value: str, expected: str, code: int) -> None:
    result = run("ids", "check", value)
    assert result.exit_code == code and expected in result.output
