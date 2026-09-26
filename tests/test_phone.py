import pytest
from hypothesis import given
from hypothesis import strategies as st

from cedikit import InvalidPhoneNumber, phone

ALL_PREFIXES = ["24", "25", "53", "54", "55", "59", "20", "50", "26", "27", "56", "57"]

national_numbers = st.builds(
    lambda p, rest: p + rest,
    st.sampled_from(ALL_PREFIXES),
    st.text(alphabet="0123456789", min_size=7, max_size=7),
)


@pytest.mark.parametrize(
    "raw",
    [
        "0244123456",
        "+233244123456",
        "+233 24 412 3456",
        "233244123456",
        "00233244123456",
        "244123456",
        "24 412 3456",
        "024-412-3456",
        "(024) 412.3456",
        " 024 412 3456 ",
        "+233 (0)24 412 3456",
        "+2330244123456",
        "024\u00a0412\u00a03456",
        244123456,
    ],
)
def test_normalise_accepts_common_formats(raw: object) -> None:
    assert phone.normalise(raw) == "+233244123456"  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ("", "empty"),
        ("   ", "empty"),
        ("02441234", "digits"),
        ("024412345678", "digits"),
        ("+234244123456", "country code"),
        ("0214123456", "prefix"),  # 021 is an Accra landline code
        ("0231234567", "prefix"),  # 023 (Glo) is deliberately not supported
        ("024412345a", "not digits"),
        ("hello", "not digits"),
    ],
)
def test_normalise_rejects_with_reason(raw: str, reason: str) -> None:
    with pytest.raises(InvalidPhoneNumber) as exc:
        phone.normalise(raw)
    assert reason in exc.value.reason
    assert isinstance(exc.value, ValueError)


@pytest.mark.parametrize("bad", [None, 2.44e8, True, ["0244123456"]])
def test_normalise_rejects_wrong_types(bad: object) -> None:
    with pytest.raises(InvalidPhoneNumber):
        phone.normalise(bad)  # type: ignore[arg-type]


def test_normalize_alias() -> None:
    assert phone.normalize("0244123456") == "+233244123456"


def test_is_valid() -> None:
    assert phone.is_valid("0244123456")
    assert not phone.is_valid("02441234")
    assert not phone.is_valid(None)


@pytest.mark.parametrize(
    ("style", "expected"),
    [
        ("e164", "+233244123456"),
        ("local", "0244123456"),
        ("pretty", "024 412 3456"),
        ("international", "+233 24 412 3456"),
    ],
)
def test_format_styles(style: phone.PhoneStyle, expected: str) -> None:
    assert phone.format("0244123456", style) == expected


def test_format_default_and_bad_style() -> None:
    assert phone.format("0244123456") == "+233244123456"
    with pytest.raises(ValueError, match="Unknown style"):
        phone.format("0244123456", "fancy")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("number", "network"),
    [
        ("0244123456", "MTN"),
        ("0501234567", "TELECEL"),
        ("0271234567", "AT"),
        ("0591234567", "MTN"),
    ],
)
def test_likely_network(number: str, network: str) -> None:
    guess = phone.likely_network(number)
    assert guess.network == network
    assert guess.certainty == "likely"
    assert "ported" in guess.note


def test_likely_network_invalid_does_not_raise() -> None:
    guess = phone.likely_network("12345")
    assert guess.network is None
    assert guess.certainty == "unknown"


def test_mask() -> None:
    assert phone.mask("0244123456") == "024****456"
    assert phone.mask("+233244123456", visible_start=0, visible_end=2, char="#") == "########56"
    with pytest.raises(ValueError):
        phone.mask("0244123456", visible_start=6, visible_end=6)
    with pytest.raises(InvalidPhoneNumber):
        phone.mask("12345")


def test_clean_column() -> None:
    report = phone.clean_column(
        ["+233244123456", "024 412 3456", "12345", None, float("nan"), 244123456.0, ""]
    )
    assert report.cleaned == [
        "+233244123456",
        "+233244123456",
        None,
        None,
        None,
        "+233244123456",
        None,
    ]
    assert (report.valid_count, report.fixed_count, report.invalid_count) == (1, 2, 4)
    assert report.invalid[1].reason == "missing value"
    assert str(report) == "7 numbers: 1 valid, 2 fixed, 4 invalid"


@given(national_numbers, st.sampled_from(["e164", "local", "pretty", "international"]))
def test_format_roundtrip(national: str, style: phone.PhoneStyle) -> None:
    e164 = "+233" + national
    assert phone.normalise(phone.format(e164, style)) == e164


@given(st.text(max_size=20))
def test_normalise_never_crashes_unexpectedly(text: str) -> None:
    try:
        result = phone.normalise(text)
    except InvalidPhoneNumber:
        return
    assert result.startswith("+233") and len(result) == 13
