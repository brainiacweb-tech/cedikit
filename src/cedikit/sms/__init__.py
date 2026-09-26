"""Parse Mobile Money transaction SMS (MTN MoMo and Telecel Cash) into structured data.

Example:
    >>> from cedikit import sms
    >>> result = sms.parse(message_text, sender="MobileMoney")  # doctest: +SKIP
    >>> if result.ok:  # doctest: +SKIP
    ...     print(result.transaction.amount, result.transaction.counterparty)
"""

from cedikit.sms.models import Counterparty, ParseResult, Transaction, TransactionType
from cedikit.sms.parser import GHANA_TIME, Parser, Template, clean, parse, parse_many

__all__ = [
    "GHANA_TIME",
    "Counterparty",
    "ParseResult",
    "Parser",
    "Template",
    "Transaction",
    "TransactionType",
    "clean",
    "parse",
    "parse_many",
]
