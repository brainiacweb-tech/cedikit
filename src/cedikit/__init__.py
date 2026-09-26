"""cedikit - a Python toolkit for Ghanaian phone numbers, cedi amounts and Mobile Money data.

Everything runs offline; no data leaves the device.
"""

from cedikit import fees, fraud, ids, ledger, money, ocr, phone, sms
from cedikit.exceptions import (
    CedikitError,
    CediTypeError,
    InvalidIdentifier,
    InvalidPhoneNumber,
    MoneyParseError,
    TemplateError,
)
from cedikit.money import Cedi

__version__ = "1.1.0"

__all__ = [
    "Cedi",
    "CediTypeError",
    "CedikitError",
    "InvalidIdentifier",
    "InvalidPhoneNumber",
    "MoneyParseError",
    "TemplateError",
    "__version__",
    "fees",
    "fraud",
    "ids",
    "ledger",
    "money",
    "ocr",
    "phone",
    "sms",
]
