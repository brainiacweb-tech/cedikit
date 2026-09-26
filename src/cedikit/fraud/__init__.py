"""Detect likely fake Mobile Money payment alerts and explain why.

Results are risk indicators, not guarantees. Always confirm a payment in the
official Mobile Money app before releasing goods.

Example:
    >>> from cedikit import fraud
    >>> report = fraud.check(message_text, sender="0551234567")  # doctest: +SKIP
    >>> print(report)  # doctest: +SKIP
    Risk: HIGH (score 0.97)
    Reasons:
      - Sent from a personal phone number ...
"""

from cedikit.fraud.rules import ADVICE, FraudReport, Signal, check, risk_level

__all__ = ["ADVICE", "FraudReport", "Signal", "check", "risk_level"]
