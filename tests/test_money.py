from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from cedikit import Cedi, CediTypeError, MoneyParseError, money

pesewa_amounts = st.decimals(
    min_value=Decimal("-999999999999.99"),
    max_value=Decimal("999999999999.99"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("GHS 1,200.50", "1200.50"),
        ("GH₵1.2k", "1200.00"),
        ("GH¢ 5", "5.00"),
        ("Ghc 20", "20.00"),
        ("ghs20", "20.00"),
        ("₵ 3.5", "3.50"),
        ("1200 cedis", "1200.00"),
        ("1 cedi", "1.00"),
        ("1,200", "1200.00"),
        ("50p", "0.50"),
        ("50 pesewas", "0.50"),
        ("1 pesewa", "0.01"),
        ("1,200.50 GHS", "1200.50"),
        ("2.5m", "2500000.00"),
        ("1.2 million", "1200000.00"),
        ("3bn", "3000000000.00"),
        ("-GHS 5", "-5.00"),
        ("GHS -5", "-5.00"),
        ("(GHS 5.00)", "-5.00"),
        (".5", "0.50"),
        ("  GHS   10  ", "10.00"),
        ("2.345", "2.35"),
        (1200, "1200.00"),
        (Decimal("7.1"), "7.10"),
        (Cedi("4"), "4.00"),
    ],
)
def test_parse(text: object, expected: str) -> None:
    result = money.parse(text)  # type: ignore[arg-type]
    assert result == Decimal(expected)
    assert result.as_tuple().exponent == -2


@pytest.mark.parametrize(
    "text",
    ["", "abc", "GHS", "1,20", "1.2.3", "--5", "-GHS -5", "GHS 50p", "12 dollars", "1" * 40],
)
def test_parse_rejects(text: str) -> None:
    with pytest.raises(MoneyParseError):
        money.parse(text)


@pytest.mark.parametrize("bad", [1.5, True])
def test_floats_and_bools_rejected(bad: object) -> None:
    with pytest.raises(CediTypeError, match="not"):
        money.parse(bad)  # type: ignore[arg-type]
    with pytest.raises(CediTypeError):
        money.format(bad)  # type: ignore[arg-type]


def test_other_types_rejected() -> None:
    with pytest.raises(CediTypeError):
        money.parse([1])  # type: ignore[arg-type]
    with pytest.raises(MoneyParseError):
        money.parse(Decimal("NaN"))


def test_round_pesewas_modes() -> None:
    assert money.round_pesewas("2.345") == Decimal("2.35")
    assert money.round_pesewas("2.345", mode="bankers") == Decimal("2.34")
    assert money.round_pesewas("2.355", mode="bankers") == Decimal("2.36")
    with pytest.raises(ValueError):
        money.round_pesewas("1", mode="up")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("amount", "style", "expected"),
    [
        ("1200.5", "symbol", "GH₵ 1,200.50"),
        ("1200.5", "code", "GHS 1,200.50"),
        ("-1200.5", "symbol", "-GH₵ 1,200.50"),
        ("0", "symbol", "GH₵ 0.00"),
        ("1200", "compact", "GH₵ 1.2k"),
        ("1000", "compact", "GH₵ 1k"),
        ("950", "compact", "GH₵ 950.00"),
        ("2500000", "compact", "GH₵ 2.5M"),
        ("999950", "compact", "GH₵ 1M"),
        ("3200000000", "compact", "GH₵ 3.2B"),
        ("-1500", "compact", "-GH₵ 1.5k"),
        ("1250", "compact", "GH₵ 1.3k"),
    ],
)
def test_format(amount: str, style: money.MoneyStyle, expected: str) -> None:
    assert money.format(amount, style) == expected


def test_format_bad_style() -> None:
    with pytest.raises(ValueError, match="Unknown style"):
        money.format("1", "fancy")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        ("1200.50", "One thousand two hundred Ghana cedis and fifty pesewas"),
        ("1", "One Ghana cedi"),
        ("0.01", "One pesewa"),
        ("0.05", "Five pesewas"),
        ("0", "Zero Ghana cedis"),
        ("105", "One hundred and five Ghana cedis"),
        ("1005", "One thousand and five Ghana cedis"),
        ("21.99", "Twenty-one Ghana cedis and ninety-nine pesewas"),
        ("2000000", "Two million Ghana cedis"),
        (
            "1234567",
            "One million two hundred and thirty-four thousand five hundred and sixty-seven Ghana cedis",  # noqa: E501
        ),
        ("3000000000000", "Three trillion Ghana cedis"),
        ("-15", "Minus fifteen Ghana cedis"),
    ],
)
def test_to_words(amount: str, expected: str) -> None:
    assert money.to_words(amount) == expected


def test_to_words_too_large() -> None:
    with pytest.raises(ValueError, match="too large"):
        money.to_words("1000000000000000")


class TestCedi:
    def test_construct_and_repr(self) -> None:
        assert repr(Cedi("12.5")) == "Cedi('12.50')"
        assert Cedi().amount == Decimal("0.00")
        assert str(Cedi("1200.5")) == "GH₵ 1,200.50"

    def test_float_rejected(self) -> None:
        with pytest.raises(CediTypeError):
            Cedi(1.5)  # type: ignore[arg-type]
        with pytest.raises(CediTypeError):
            Cedi("1") + 0.5
        with pytest.raises(CediTypeError):
            _ = Cedi("1") < 0.5

    def test_arithmetic(self) -> None:
        assert Cedi("1.10") + Cedi("2.20") == Cedi("3.30")
        assert sum([Cedi("1.10"), Cedi("2.20")]) == Cedi("3.30")
        assert Cedi("5") - 2 == Cedi("3")
        assert 10 - Cedi("4") == Cedi("6")
        assert Cedi("12.50") * 3 == Cedi("37.50")
        assert Decimal("0.015") * Cedi("100") == Cedi("1.50")
        assert Cedi("10") / 3 == Cedi("3.33")
        assert Cedi("10") / Cedi("4") == Decimal("2.5")
        assert -Cedi("5") == Cedi("-5")
        assert +Cedi("5") == Cedi("5")
        assert abs(Cedi("-5")) == Cedi("5")

    def test_invalid_operations(self) -> None:
        with pytest.raises(TypeError):
            Cedi("2") * Cedi("3")
        with pytest.raises(ZeroDivisionError):
            Cedi("2") / 0
        with pytest.raises(TypeError):
            Cedi("2") + "3"  # type: ignore[operator]
        with pytest.raises(TypeError):
            "3" - Cedi("2")  # type: ignore[operator]
        with pytest.raises(TypeError):
            Cedi("2") * "3"  # type: ignore[operator]
        with pytest.raises(TypeError):
            Cedi("2") / "3"  # type: ignore[operator]
        with pytest.raises(TypeError):
            _ = Cedi("2") < "3"  # type: ignore[operator]

    def test_comparison_and_hash(self) -> None:
        assert Cedi("1") < Cedi("2") <= 2 < Cedi("3")
        assert Cedi("3") > 2 and Cedi("3") >= Cedi("3")
        assert Cedi("2") == 2 == Cedi("2.00")
        assert Cedi("2") != 2.0
        assert Cedi("2") != True  # noqa: E712
        assert Cedi("2") != "2"
        assert len({Cedi("2"), Cedi("2.00")}) == 1
        assert not Cedi("0") and Cedi("0.01")

    def test_immutable(self) -> None:
        with pytest.raises(AttributeError):
            Cedi("1")._amount = Decimal("2")  # type: ignore[misc]

    def test_format_protocol_and_words(self) -> None:
        c = Cedi("1500")
        assert f"{c}" == "GH₵ 1,500.00"
        assert f"{c:code}" == "GHS 1,500.00"
        assert f"{c:compact}" == "GH₵ 1.5k"
        assert f"{c:.1f}" == "1500.0"
        assert c.to_words() == "One thousand five hundred Ghana cedis"


@given(pesewa_amounts, st.sampled_from(["symbol", "code"]))
def test_format_parse_roundtrip(amount: Decimal, style: money.MoneyStyle) -> None:
    assert money.parse(money.format(amount, style)) == amount


@given(st.lists(pesewa_amounts, max_size=50))
def test_cedi_sum_is_exact(amounts: list[Decimal]) -> None:
    assert sum((Cedi(a) for a in amounts), Cedi()).amount == sum(amounts, Decimal(0))


@given(st.decimals(min_value=0, max_value=Decimal("999999999.99"), places=2))
def test_to_words_never_fails(amount: Decimal) -> None:
    words = money.to_words(amount)
    assert words[0].isupper()
    assert "cedi" in words or "pesewa" in words
