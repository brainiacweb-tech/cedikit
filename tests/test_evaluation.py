from pathlib import Path
from typing import Any

import pytest

from cedikit import evaluation, fraud
from cedikit.fraud.classifier import ScamClassifier

Samples = dict[str, dict[str, Any]]


def test_parser_meets_target(genuine: Samples) -> None:
    result = evaluation.evaluate_parser(list(genuine.values()))
    assert result.accuracy == 1.0
    assert "meets target" in str(result)


def test_parser_failures_are_reported(genuine: Samples) -> None:
    wrong = {**genuine["mtn_cash_out"], "expected": {"amount": "41.00"}}
    result = evaluation.evaluate_parser([wrong, {"id": "x", "text": "hello"}])
    assert result.fully_correct == 0
    assert result.failures["x"] == ["not recognised"]
    assert "amount: expected Decimal('41.00')" in result.failures["mtn_cash_out"][0]
    assert "below target" in str(result)


def test_fraud_evaluation(genuine: Samples, scam: Samples) -> None:
    result = evaluation.evaluate_fraud(list(genuine.values()), list(scam.values()))
    assert (result.recall, result.precision) == (1.0, 1.0)
    assert result.f1 == 1.0
    text = str(result)
    assert "Recall:    100.0% (meets target)" in text and "too few" in text


def test_fraud_evaluation_counts_mistakes(genuine: Samples) -> None:
    alarm = {**genuine["mtn_cash_out"], "id": "copy", "sender": "0551234567"}
    missed = {"id": "quiet", "text": "Hello, see you soon.", "sender": None}
    result = evaluation.evaluate_fraud([alarm], [missed], flag_at="HIGH")
    assert (result.false_positives, result.false_negatives) == (1, 1)
    assert result.precision == 0.0 and result.recall == 0.0 and result.f1 == 0.0
    assert "MISSED: quiet" in str(result) and "FALSE ALARM: copy" in str(result)


def test_load_rejects_non_lists(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("a: 1", encoding="utf-8")
    with pytest.raises(ValueError, match="list"):
        evaluation.load(path)


def test_classifier(genuine: Samples, scam: Samples, tmp_path: Path) -> None:
    pytest.importorskip("sklearn")
    model = ScamClassifier.train(
        [s["text"] for s in genuine.values()], [s["text"] for s in scam.values()]
    )
    assert model.trained_on == (len(genuine), len(scam))
    fake = "Sorry dear your account is blocked, do not try your pin. Cash receive for 50.00"
    real = genuine["mtn_received"]["text"]
    assert model.probability(fake) > 0.5 > model.probability(real)

    path = tmp_path / "model.joblib"
    model.save(path)
    loaded = ScamClassifier.load(path)
    assert loaded.probability(fake) == pytest.approx(model.probability(fake))

    flagged = fraud.check(fake, classifier=loaded)
    assert flagged.checks["ml_classifier"] is False
    assert any("labelled messages rates this" in r for r in flagged.reasons)
    passed = fraud.check(real, sender="MobileMoney", classifier=loaded)
    assert passed.checks["ml_classifier"] is True and passed.risk == "LOW"

    with_model = evaluation.evaluate_fraud(
        list(genuine.values()), list(scam.values()), classifier=model
    )
    assert with_model.recall == 1.0

    with pytest.raises(ValueError, match="at least two"):
        ScamClassifier.train(["a"], ["b", "c"])
