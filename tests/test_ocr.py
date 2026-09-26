from typing import Any

import pytest

from cedikit import ocr, sms
from cedikit.ocr import OcrLine, fix_ocr_text, group_messages

H = 30  # line height used by the simulated screens below


def _screen(rows: list[tuple[float, str]], x: float = 40) -> list[OcrLine]:
    """Simulated OCR output: (y, text) pairs on a 1000-pixel-tall screen."""
    return [OcrLine(text, x, y, 400, H) for y, text in rows]


@pytest.mark.parametrize(
    ("raw", "fixed"),
    [
        ("Cash Out made for GHS50.OO", "Cash Out made for GHS50.00"),
        ("balance is GHSO.20. Your E-levy", "balance is GHS0.20. Your E-levy"),
        ("Fee charged: GHS O. Cash in", "Fee charged: GHS 0. Cash in"),
        ("Current Balance GH5 444.26", "Current Balance GHS 444.26"),
        ("Financial Transaction ld: 191", "Financial Transaction Id: 191"),
        ("Transaction D: 1919", "Transaction ID: 1919"),
        ("Transaction 11): 6292", "Transaction ID: 6292"),
        ("TRANSACTION FEE: O.OO", "TRANSACTION FEE: 0.00"),
        ("GHS0.00,Tax Charged O.Download", "GHS0.00,Tax Charged 0.Download"),
        ("balance is 1O4.5O today", "balance is 104.50 today"),
        # names and ordinary words are left alone
        ("from KOFI ODOOM", "from KOFI ODOOM"),
        ("Loan .Current Balance", "Loan .Current Balance"),
    ],
)
def test_fix_ocr_text(raw: str, fixed: str) -> None:
    assert fix_ocr_text(raw) == fixed


def test_groups_bubbles_and_reads_sender() -> None:
    lines = _screen(
        [
            (10, "10:24"),
            (12, "O .lll .111 C"),  # status icons
            (70, "MobileMoney"),
            (160, "Today 10:04 AM"),
            (220, "Payment received for GHS 20.00 from"),
            (255, "KOJO MENSAH Current Balance: GHS 50.00 ."),
            (290, "Available Balance: GHS 50.00. Transaction ID: 51234567890."),
            (325, "TRANSACTION FEE: O.OO"),
            (420, "Payment received for GHS 5.00 from"),  # gap of 65px > 1.3 lines
            (455, "AMA OWUSU Current Balance: GHS 55.00 ."),
            (490, "Available Balance: GHS 55.00. Transaction ID: 51234567891."),
            (525, "TRANSACTION FEE: 0.00"),
            (600, ". MTN"),
            (900, "Sender can't accept replies. Contact them"),
            (930, "directly. Learn more"),
        ]
    )
    messages, sender = group_messages(lines, 1000)
    assert sender == "MobileMoney"
    assert len(messages) == 2
    assert all(sms.parse(m, sender).ok for m in messages)
    assert messages[0].endswith("TRANSACTION FEE: 0.00")


def test_phone_number_sender_and_chrome_between_bubbles() -> None:
    lines = _screen(
        [
            (60, "+233 54 123 4567"),
            (100, "Text Message • SMS"),
            (130, "16:06"),
            (200, "Cash receive for 200.00 form KOFI"),
            (235, "we dey for you."),
            (270, "16:07"),  # a time stamp between two bubbles also splits them
            (305, "Reversal of 200.00 have been made on your number"),
            (340, "your balance is GHSO.OO"),
        ]
    )
    messages, sender = group_messages(lines, 1000)
    assert sender == "+233 54 123 4567"
    assert messages == [
        "Cash receive for 200.00 form KOFI we dey for you.",
        "Reversal of 200.00 have been made on your number your balance is GHS0.00",
    ]


def test_notification_header_gives_sender() -> None:
    lines = _screen(
        [
            (500, "MobileMoney • Messages • now"),
            (535, "Cash In received for GHS 10.00 from ADOM VENTURES."),
            (570, "Current Balance GHS 20.00 Available Balance GHS 20.00."),
        ]
    )
    messages, sender = group_messages(lines, 1000)
    assert sender == "MobileMoney"
    assert messages[0].startswith("Cash In received")


def test_message_starting_high_on_a_scrolled_screen_is_kept() -> None:
    lines = _screen(
        [
            (10, "12:48"),
            (60, "T-CASH"),
            (120, "0000019288776655"),  # in the top part of the screen, but below the header
            (155, "Confirmed. On 2026-01-12 at 08:08:20, a deposit of"),
        ]
    )
    messages, sender = group_messages(lines, 1000)
    assert sender == "T-CASH"
    assert messages[0].startswith("0000019288776655 Confirmed.")


def test_nothing_useful() -> None:
    assert group_messages([], 1000) == ([], None)
    assert group_messages(_screen([(10, "12:00"), (500, "hello")]), 1000) == ([], None)


def test_readings_resize_when_text_is_too_big() -> None:
    from PIL import Image

    calls: list[tuple[int, int]] = []

    def fake_engine(img: Any) -> list[OcrLine]:
        calls.append(img.size)
        height = 44 if img.size == (900, 2000) else 22
        return [OcrLine("text", 10, 100, 200, height)]

    readings = ocr._readings(Image.new("RGB", (900, 2000)), fake_engine)
    assert calls == [(900, 2000), (450, 1000)]
    assert len(readings) == 2
    assert readings[1][0].y == pytest.approx(200)  # y=100 at half size is y=200 originally

    calls.clear()
    readings = ocr._readings(Image.new("RGB", (450, 1000)), fake_engine)
    assert calls == [(450, 1000)] and len(readings) == 1
    assert ocr._readings(Image.new("RGB", (10, 10)), lambda _img: []) == [[]]


def test_read_screenshot_rejects_non_images() -> None:
    if ocr.available_engine() is None:
        pytest.skip("no OCR engine installed")
    with pytest.raises(OSError):
        ocr.read_screenshot(b"not an image")


def test_read_sample_screenshot_end_to_end(tmp_path: Any) -> None:
    if ocr.available_engine() is None:
        pytest.skip("no OCR engine installed")
    from cedikit.app.common import sample_screenshot

    png = sample_screenshot()
    path = tmp_path / "shot.png"
    path.write_bytes(png)
    for image in (png, path, str(path)):
        shot = ocr.read_screenshot(image)
        assert shot.sender == "MobileMoney"
        assert len(shot.messages) == 2
        assert all(sms.parse(m, shot.sender).ok for m in shot.messages)
        assert shot.lines and shot.engine
