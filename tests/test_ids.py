from importlib import resources

import pytest
import yaml

from cedikit import InvalidIdentifier
from cedikit.ids import ghana_card, gpgps

# -- Ghana Card -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected", "kind"),
    [
        ("GHA-123456789-0", "GHA-123456789-0", "citizen"),
        ("gha1234567890", "GHA-123456789-0", "citizen"),
        (" GHA 123456789 0 ", "GHA-123456789-0", "citizen"),
        ("FGN-987654321-5", "FGN-987654321-5", "foreign national"),
        ("fgn9876543215", "FGN-987654321-5", "foreign national"),
    ],
)
def test_ghana_card_normalise(raw: str, expected: str, kind: str) -> None:
    assert ghana_card.normalise(raw) == expected
    assert ghana_card.is_valid_format(raw)
    assert ghana_card.card_type(raw) == kind


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ("GHA-12345678-0", "9 digits"),
        ("GHA-123456789-01", "9 digits"),
        ("NIG-123456789-0", "not a Ghana Card prefix"),
        ("", "9 digits"),
        (123, "must be text"),
    ],
)
def test_ghana_card_invalid(raw: object, reason: str) -> None:
    assert not ghana_card.is_valid_format(raw)
    with pytest.raises(InvalidIdentifier, match=reason):
        ghana_card.normalise(raw)  # type: ignore[arg-type]


def test_ghana_card_mask() -> None:
    assert ghana_card.mask("GHA-123456789-0") == "GHA-12*****89-0"
    assert ghana_card.mask("fgn9876543215") == "FGN-98*****21-5"


# -- GhanaPostGPS -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "code", "region", "district"),
    [
        ("AK-039-5028", "AK-039-5028", "Ashanti", "Kumasi Metropolitan"),
        ("ak0395028", "AK-039-5028", "Ashanti", "Kumasi Metropolitan"),
        ("GA 183 8164", "GA-183-8164", "Greater Accra", "Accra Metropolitan"),
        ("GY-123-4567", "GY-123-4567", "Greater Accra", "Ada East"),
        # district "codes" can end in a digit
        ("A2-123-4567", "A2-123-4567", "Ashanti", "Adansi North"),
        ("n31234567", "N3-123-4567", "Northern, Savannah and North East", "Central Gonja"),
        # area codes may be longer than 3 digits
        ("XW-0123-4567", "XW-0123-4567", "Upper West", "Wa Municipal"),
        ("VH123454567", "VH-12345-4567", "Volta and Oti", "Ho Municipal"),
        # a district missing from the table still parses
        ("G9-123-4567", "G9-123-4567", "Greater Accra", None),
    ],
)
def test_gpgps_parse(raw: str, code: str, region: str, district: str | None) -> None:
    address = gpgps.parse(raw)
    assert (address.code, str(address)) == (code, code)
    assert (address.region, address.district) == (region, district)
    assert gpgps.is_valid_format(raw)


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ("ZZ-039-5028", "region letter"),
        ("AK-39-5028", "format"),  # area too short
        ("AK-039-502", "format"),  # unique code must be 4 digits
        ("AK-123456-5028", "format"),  # area too long
        ("A-039-5028", "format"),
    ],
)
def test_gpgps_invalid(raw: str, reason: str) -> None:
    with pytest.raises(InvalidIdentifier, match=reason):
        gpgps.parse(raw)
    assert not gpgps.is_valid_format(raw)
    assert not gpgps.is_valid_format(None)


def test_region_and_district_names() -> None:
    assert gpgps.region_name("G") == "Greater Accra"
    assert gpgps.region_name("va-123-4567") == "Volta and Oti"
    assert gpgps.region_name("Q") is None
    assert gpgps.region_name("") is None
    assert gpgps.district_name("GT") == "Tema Metropolitan"
    assert gpgps.district_name("no-123-4567") == "Nanumba South"
    assert gpgps.district_name("") is None


def test_every_code_in_the_data_file_is_well_formed() -> None:
    """Guards against YAML surprises such as a bare NO key loading as False."""
    text = resources.files("cedikit.ids").joinpath("regions.yaml").read_text("utf-8")
    data = yaml.safe_load(text)
    for code in data["districts"]:
        assert isinstance(code, str) and len(code) == 2, code
        assert code[0] in data["regions"], code
