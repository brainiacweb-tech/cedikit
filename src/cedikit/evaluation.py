"""Measure the parser and fraud checker against labelled, anonymised messages.

The file format is the one used by ``tests/fixtures/sample_messages``: a YAML
list of entries with ``text``, ``sender`` and (for parser checks) ``expected``
fields. Keep a held-out set that is never used to tune rules or train models.

Example::

    from cedikit import evaluation
    genuine = evaluation.load("genuine.yaml")
    scam = evaluation.load("scam.yaml")
    print(evaluation.evaluate_fraud(genuine, scam))
    print(evaluation.evaluate_parser(genuine))
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from cedikit import fraud, sms
from cedikit.fraud.rules import FraudReport, Risk

if TYPE_CHECKING:
    from cedikit.fraud.classifier import ScamClassifier

__all__ = ["FraudEvaluation", "ParserEvaluation", "evaluate_fraud", "evaluate_parser", "load"]

RECALL_TARGET = 0.90
PRECISION_TARGET = 0.85
PARSER_TARGET = 0.95
_MONEY_FIELDS = {"amount", "fee", "tax", "balance", "available_balance"}
_ORDER: dict[str, int] = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def load(path: str | Path) -> list[dict[str, Any]]:
    """Load a labelled YAML file."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a list of messages")
    return data


def _ratio(a: int, b: int) -> float:
    return a / b if b else 0.0


@dataclass(frozen=True)
class FraudEvaluation:
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int
    flag_at: Risk
    missed: list[tuple[dict[str, Any], FraudReport]] = field(default_factory=list)
    false_alarms: list[tuple[dict[str, Any], FraudReport]] = field(default_factory=list)

    @property
    def recall(self) -> float:
        """Share of scams that were flagged."""
        return _ratio(self.true_positives, self.true_positives + self.false_negatives)

    @property
    def precision(self) -> float:
        """Share of flagged messages that really were scams."""
        return _ratio(self.true_positives, self.true_positives + self.false_positives)

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    def __str__(self) -> str:
        total = sum(
            (self.true_positives, self.false_positives, self.true_negatives, self.false_negatives)
        )

        def mark(value: float, target: float) -> str:
            return "meets target" if value >= target else f"below target {target:.0%}"

        lines = [
            f"Fraud detection on {total} messages (flagged at {self.flag_at} or above):",
            f"  Recall:    {self.recall:.1%} ({mark(self.recall, RECALL_TARGET)})",
            f"  Precision: {self.precision:.1%} ({mark(self.precision, PRECISION_TARGET)})",
            f"  F1:        {self.f1:.3f}",
            f"  Scams caught {self.true_positives}, missed {self.false_negatives}; "
            f"false alarms {self.false_positives}, correct passes {self.true_negatives}",
        ]
        lines += [f"  MISSED: {m.get('id', m['text'][:50])}" for m, _ in self.missed]
        lines += [f"  FALSE ALARM: {m.get('id', m['text'][:50])}" for m, _ in self.false_alarms]
        if total < 100:
            lines.append(f"  Note: {total} messages is too few for reliable percentages.")
        return "\n".join(lines)


def evaluate_fraud(
    genuine: Sequence[dict[str, Any]],
    scam: Sequence[dict[str, Any]],
    *,
    flag_at: Risk = "MEDIUM",
    use_sender: bool = True,
    classifier: ScamClassifier | None = None,
) -> FraudEvaluation:
    """Count how many scams are flagged and how many genuine messages are wrongly flagged.

    Args:
        flag_at: The lowest risk level counted as "flagged".
        use_sender: Pass each message's sender to the checker. Set False to
            measure how well the text alone is judged.
    """
    tp = fp = tn = fn = 0
    missed: list[tuple[dict[str, Any], FraudReport]] = []
    alarms: list[tuple[dict[str, Any], FraudReport]] = []
    for sample, is_scam in [(g, False) for g in genuine] + [(s, True) for s in scam]:
        report = fraud.check(
            sample["text"],
            sender=sample.get("sender") if use_sender else None,
            classifier=classifier,
        )
        flagged = _ORDER[report.risk] >= _ORDER[flag_at]
        if is_scam and flagged:
            tp += 1
        elif is_scam:
            fn += 1
            missed.append((sample, report))
        elif flagged:
            fp += 1
            alarms.append((sample, report))
        else:
            tn += 1
    return FraudEvaluation(tp, fp, tn, fn, flag_at, missed, alarms)


def _actual(tx: sms.Transaction, name: str) -> Any:
    if name.startswith("counterparty_"):
        return getattr(tx.counterparty, name.removeprefix("counterparty_"), None)
    if name == "timestamp":
        return tx.timestamp.isoformat() if tx.timestamp else None
    if name == "type":
        return tx.type.value
    return getattr(tx, name)


def field_mismatches(tx: sms.Transaction, expected: dict[str, Any]) -> list[str]:
    """Fields of ``tx`` that differ from ``expected``, as readable strings."""
    problems = []
    for name, want in expected.items():
        if name in _MONEY_FIELDS and want is not None:
            want = Decimal(str(want))
        got = _actual(tx, name)
        if got != want:
            problems.append(f"{name}: expected {want!r}, got {got!r}")
    return problems


@dataclass(frozen=True)
class ParserEvaluation:
    total: int
    fully_correct: int
    failures: dict[str, list[str]] = field(default_factory=dict)

    @property
    def accuracy(self) -> float:
        return _ratio(self.fully_correct, self.total)

    def __str__(self) -> str:
        status = "meets" if self.accuracy >= PARSER_TARGET else "below"
        lines = [
            f"Parser: {self.fully_correct}/{self.total} messages with every expected field "
            f"correct ({self.accuracy:.1%}, {status} target {PARSER_TARGET:.0%})"
        ]
        for sample_id, problems in self.failures.items():
            lines.append(f"  {sample_id}: " + "; ".join(problems))
        return "\n".join(lines)


def evaluate_parser(samples: Sequence[dict[str, Any]]) -> ParserEvaluation:
    """Check that each sample parses with all its ``expected`` fields correct."""
    correct = 0
    failures: dict[str, list[str]] = {}
    for i, sample in enumerate(samples):
        sample_id = str(sample.get("id", i))
        result = sms.parse(sample["text"], sender=sample.get("sender"))
        if result.transaction is None:
            failures[sample_id] = ["not recognised"]
            continue
        problems = field_mismatches(result.transaction, sample.get("expected", {}))
        if problems:
            failures[sample_id] = problems
        else:
            correct += 1
    return ParserEvaluation(len(samples), correct, failures)
