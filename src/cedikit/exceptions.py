"""Exceptions raised by cedikit."""

from __future__ import annotations


class CedikitError(Exception):
    """Base class for all cedikit errors."""


class InvalidPhoneNumber(CedikitError, ValueError):
    """Raised when a phone number cannot be normalised to a valid Ghanaian mobile number."""

    def __init__(self, value: object, reason: str) -> None:
        self.value = value
        self.reason = reason
        super().__init__(f"Invalid Ghanaian phone number {value!r}: {reason}")


class CediTypeError(CedikitError, TypeError):
    """Raised when a float (or other unsafe type) is used as a money value."""


class InvalidIdentifier(CedikitError, ValueError):
    """Raised when a Ghana Card number or digital address has the wrong format."""

    def __init__(self, value: object, reason: str) -> None:
        self.value = value
        self.reason = reason
        super().__init__(f"Invalid identifier {value!r}: {reason}")


class TemplateError(CedikitError):
    """Raised when an SMS template file is malformed."""


class MoneyParseError(CedikitError, ValueError):
    """Raised when text cannot be parsed as a cedi amount."""

    def __init__(self, value: object, reason: str) -> None:
        self.value = value
        self.reason = reason
        super().__init__(f"Cannot parse {value!r} as a cedi amount: {reason}")
