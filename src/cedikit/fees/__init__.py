"""Estimate Mobile Money fees and the E-Levy from dated, sourced tables.

Results are always *estimates*: charges change, and the tables record only
what has been observed or published. Unknown values are ``None``, never guessed.

Example:
    >>> from datetime import date
    >>> from cedikit import fees
    >>> fees.estimate("MTN", "cash_out", "50.00").fee
    Decimal('0.50')
"""

from cedikit.fees.calculator import FeeEstimate, Kind, estimate

__all__ = ["FeeEstimate", "Kind", "estimate"]
