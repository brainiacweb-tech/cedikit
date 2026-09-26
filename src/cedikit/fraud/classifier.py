"""Optional machine-learning scam classifier (needs ``pip install 'cedikit[ml]'``).

The model is an *extra* signal for :func:`cedikit.fraud.check`, never the only
one. cedikit does not ship a trained model: train one on your own labelled,
anonymised messages (hundreds of each class, ideally) and keep a held-out set
for evaluation.

Example::

    from cedikit.fraud.classifier import ScamClassifier
    model = ScamClassifier.train(genuine_texts, scam_texts)
    model.save("scam_model.joblib")
    report = fraud.check(text, sender=sender, classifier=model)

Security: :meth:`ScamClassifier.load` uses joblib (pickle), which can run code.
Only load model files you created yourself.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from cedikit.sms.parser import clean

__all__ = ["ScamClassifier", "prepare"]

_DIGITS = re.compile(r"\d")


def prepare(text: str) -> str:
    """Normalise text so the model learns wording, not specific amounts or IDs."""
    from cedikit.fraud.rules import _plain  # local import avoids a cycle

    return _DIGITS.sub("0", _plain(clean(text)).lower())


class ScamClassifier:
    """Character n-gram TF-IDF + logistic regression.

    Character n-grams cope with typos and odd spacing ("Avaliable", "balan"),
    which word-based models would treat as unknown words.
    """

    def __init__(self, pipeline: Any, trained_on: tuple[int, int] = (0, 0)) -> None:
        self.pipeline = pipeline
        self.trained_on = trained_on  # (genuine, scam) counts

    @classmethod
    def train(cls, genuine: Iterable[str], scam: Iterable[str]) -> ScamClassifier:
        """Fit a new model. Needs at least two examples of each class."""
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline

        good, bad = [prepare(t) for t in genuine], [prepare(t) for t in scam]
        if len(good) < 2 or len(bad) < 2:
            raise ValueError("need at least two genuine and two scam messages to train")
        pipeline = make_pipeline(
            TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True),
            LogisticRegression(class_weight="balanced", max_iter=1000),
        )
        pipeline.fit(good + bad, [0] * len(good) + [1] * len(bad))
        return cls(pipeline, (len(good), len(bad)))

    def probability(self, text: str) -> float:
        """Estimated probability (0-1) that ``text`` is a scam."""
        return float(self.pipeline.predict_proba([prepare(text)])[0][1])

    def save(self, path: str | Path) -> None:
        import joblib

        joblib.dump({"pipeline": self.pipeline, "trained_on": self.trained_on}, path)

    @classmethod
    def load(cls, path: str | Path) -> ScamClassifier:
        """Load a model saved with :meth:`save`. Only load files you trust."""
        import joblib

        data = joblib.load(path)
        return cls(data["pipeline"], tuple(data["trained_on"]))
