"""Format checks for Ghanaian identifiers: Ghana Card numbers and GhanaPostGPS addresses.

These are format checks only. They never confirm that an ID or address exists.

Example:
    >>> from cedikit.ids import ghana_card, gpgps
    >>> ghana_card.is_valid_format("GHA-123456789-0")
    True
    >>> gpgps.region_name("GA-183-8164")
    'Greater Accra'
"""

from cedikit.ids import ghana_card, gpgps

__all__ = ["ghana_card", "gpgps"]
