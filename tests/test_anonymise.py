from decimal import Decimal
from typing import Any

from cedikit.ledger import Ledger
from cedikit.sms.anonymise import Anonymiser, anonymise, anonymise_many

Samples = dict[str, dict[str, Any]]


def test_personal_data_is_replaced(genuine: Samples) -> None:
    sample = genuine["telecel_sent_cross_network"]
    out = anonymise(sample["text"], sample["sender"], seed=5)
    for secret in ("KWAME ASANTE MENSAH", "0241234567", "0000019472630581", "2026-01-15", "Lunch"):
        assert secret not in out.text
    assert out.text.startswith("00000")  # leading zeros of the ID kept
    assert " 024" in out.text  # network prefix kept
    assert not out.needs_review and out.notes == []


def test_balances_still_add_up_across_a_batch(genuine: Samples) -> None:
    ids = ["telecel_sent_same_network", "telecel_received_same_network"]
    results = anonymise_many([(genuine[i]["text"], "T-CASH") for i in ids], seed=11)
    ledger = Ledger.from_messages([(r.text, "T-CASH") for r in results])
    assert len(ledger) == 2 and ledger.balance_gaps() == []


def test_same_person_gets_same_fake_name(genuine: Samples) -> None:
    ids = ["mtn_cash_out", "mtn_cash_in_same_wallet"]
    a, b = anonymise_many([genuine[i]["text"] for i in ids], seed=2)
    name = a.text.split(" to ")[1].split(" .")[0]
    assert name.endswith("ELECTRICALS") and name != "ADOM ELECTRICALS"
    assert name in b.text


def test_title_case_names_stay_title_case(genuine: Samples) -> None:
    out = anonymise(genuine["telecel_cash_in_mixed_case_name"]["text"], "T-CASH", seed=1).text
    assert "Akua Mensah Bi Nti" not in out
    assert "Enterprise ." in out


def test_numeric_reference_is_kept(genuine: Samples) -> None:
    out = anonymise(genuine["telecel_received_same_network"]["text"], "T-CASH", seed=1).text
    assert "Reference: 1." in out


def test_unparsed_messages_need_review() -> None:
    out = anonymise("Call KOFI on 0241234567 about GHS 5.00, see https://bit.ly/abc123", seed=1)
    assert out.needs_review and out.notes
    assert "0241234567" not in out.text and "https://bit.ly/xxxxxx" in out.text


def test_explicit_scale_and_shift() -> None:
    anon = Anonymiser(scale=Decimal("2"), day_shift=1)
    out = anon("Paid GHS 1,250.50 and 3.25 on 2026-02-28, GHS 0. Bad date 2026-02-31.").text
    assert out == "Paid GHS 2,501.00 and 6.50 on 2026-03-01, GHS 0. Bad date 2026-02-31."


def test_seed_is_reproducible(genuine: Samples) -> None:
    text = genuine["mtn_received"]["text"]
    assert anonymise(text, seed=9) == anonymise(text, seed=9)
