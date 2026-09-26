"""Read Mobile Money messages from screenshots (OCR), offline.

Needs ``pip install "cedikit[ocr]"``. On Windows it uses the OCR engine built into
Windows; elsewhere it uses RapidOCR. Both run entirely on this computer.

A screenshot of a messaging app holds more than the message: the clock, the
sender's name, "Today 10:04 AM", "Sender can't accept replies"... and often
several messages. :func:`read_screenshot` keeps only the message bubbles, splits
them into separate messages, fixes common OCR slips (``GHS50.OO`` -> ``GHS50.00``)
and picks out the sender shown at the top of the screen.

Example::

    from cedikit import ocr, fraud

    shot = ocr.read_screenshot("screenshot.png")
    for message in shot.messages:
        print(fraud.check(message, sender=shot.sender).risk)

OCR can misread text: always compare the result with the picture.
"""

from __future__ import annotations

import io
import re
import statistics
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cedikit.exceptions import CedikitError
from cedikit.sms.parser import _default_parser

__all__ = [
    "OcrLine",
    "OcrUnavailable",
    "Screenshot",
    "available_engine",
    "fix_ocr_text",
    "group_messages",
    "read_screenshot",
]

ImageInput = str | Path | bytes


class OcrUnavailable(CedikitError):
    """Raised when no OCR engine is installed."""


@dataclass(frozen=True)
class OcrLine:
    """One line of text found in an image, with its position in pixels."""

    text: str
    x: float
    y: float
    width: float
    height: float

    @property
    def bottom(self) -> float:
        return self.y + self.height


@dataclass(frozen=True)
class Screenshot:
    """What was read from a screenshot.

    Attributes:
        messages: The message bubbles, top to bottom, as text (OCR slips fixed).
        sender: The sender shown at the top of the screen, if one was recognised
            (an official sender ID such as ``MobileMoney``, or a phone number).
        engine: Which OCR engine was used.
        lines: Every line the engine found (for troubleshooting).
    """

    messages: list[str]
    sender: str | None
    engine: str
    lines: list[OcrLine] = field(default_factory=list)


# -- fixing OCR slips ---------------------------------------------------------------------

_DIGITISH = str.maketrans({"O": "0", "o": "0", "Q": "0", "D": "0", "I": "1", "l": "1", "|": "1"})
_MONEY = re.compile(
    r"(GH ?[S5$₵¢C] ?)([0-9OoQIl|][0-9OoQIl|,]*(?:\.[0-9OoQDIl|]{1,2})?)(?![A-Za-z])"
)
_DECIMAL = re.compile(r"(?<![\w.])([0-9Oo]*[0-9][0-9Oo]*\.[0-9Oo]{2})(?![\w])")
_WORD_FIXES = [
    (re.compile(r"\bGH5\b|\bGH\$"), "GHS"),
    (re.compile(r"\bTransaction ld\b"), "Transaction Id"),
    (re.compile(r"\bTransaction [lI1|]?D:"), "Transaction ID:"),
    (re.compile(r"\bTransaction [1lI|]{2}\)?:"), "Transaction ID:"),
    (re.compile(r"\bTRANSACTION FEE: ?O\.OO\b"), "TRANSACTION FEE: 0.00"),
    (re.compile(r"\b(Tax Charged|Fee charged:?) [Oo](?=[.,\s]|$)"), r"\1 0"),
]


def fix_ocr_text(text: str) -> str:
    """Undo common OCR confusions in MoMo messages, mainly letters read in numbers.

    Only money amounts and a few fixed phrases are touched, so names and other
    words are left exactly as read.

    Example:
        >>> fix_ocr_text("Cash Out made for GHS50.OO. Financial Transaction ld: 191")
        'Cash Out made for GHS50.00. Financial Transaction Id: 191'
    """
    for pattern, replacement in _WORD_FIXES:
        text = pattern.sub(replacement, text)
    text = _MONEY.sub(lambda m: "GHS" + m[1][3:].replace("5", "") + m[2].translate(_DIGITISH), text)
    return _DECIMAL.sub(lambda m: m[1].translate(_DIGITISH), text)


# -- turning lines into messages ----------------------------------------------------------

_CHROME = re.compile(
    r"""^(
        \d{1,2}:\d{2}(\s?[AaPp]\.?[Mm]\.?)?\s*[•·.]?      # clock
      | (Today|Yesterday|Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\s*(\d.*|[•·].*)?  # date lines
      | .*\b(Text\ Message|Message\ •\ SMS|SMS|iMessage)\b.*
      | .*Sender\ can't\ accept\ replies.* | .*directly\.\ Learn\ more.*
      | .*(Enter|Type)\ (a\ )?message.* | .*[•·]\s*Messages\s*[•·].*
      | Mark\ as\ read | Delivered | Read
      | [.•·\-]*\s*(Telecel|MTN|AT|MobileMoney|T-CASH)?\s*[.•·]?   # bubble footers
      | LTE | 4G | 5G | \W{0,3}\w{0,2}\W{0,3}                # status icons, stray marks
    )$""",
    re.IGNORECASE | re.VERBOSE,
)
_PHONE_LIKE = re.compile(r"^\+?\d[\d\s\-()]{8,}\d$")
_GAP = 1.3  # a vertical gap this many line-heights wide starts a new message
_HEADER = 0.16  # the top part of the screen that holds the clock and sender


_WORD = re.compile(r"[A-Za-z]{4,}")


def _is_chrome(text: str) -> bool:
    return bool(_CHROME.match(text.strip()))


def _header_bottom(lines: Sequence[OcrLine], image_height: float, sender: str | None) -> float:
    """Where the screen's header (clock, sender name) ends; 0 if there isn't one.

    Only lines up to the lowest clock or sender line near the top count as header,
    so a message that starts high up (a scrolled screenshot) is kept.
    """
    marks = [
        line.bottom
        for line in lines
        if line.y < image_height * _HEADER
        and (line.text.strip() == sender or _is_chrome(line.text))
    ]
    return max(marks, default=0.0)


def _is_header_noise(line: OcrLine, header_bottom: float, sender: str | None) -> bool:
    """Clock, signal icons and the sender's name at the top of the screen."""
    if line.y >= header_bottom:
        return False
    text = line.text.strip()
    return text == sender or _is_chrome(text) or not _WORD.search(text)


def _find_sender(lines: Sequence[OcrLine], height: float) -> str | None:
    parser = _default_parser()
    for line in lines:  # a notification header: "MobileMoney • Messages • now"
        first = re.split(r"\s*[•·]\s*", line.text.strip())[0]
        if "•" in line.text and parser.is_official_sender(first):
            return next(s for s in parser.sender_ids if s.casefold() == first.casefold())
    for line in lines:
        if line.y > height * _HEADER:
            break
        text = line.text.strip()
        if parser.is_official_sender(text):
            return next(s for s in parser.sender_ids if s.casefold() == text.casefold())
        if _PHONE_LIKE.match(text):
            return text
    return None


def group_messages(lines: Sequence[OcrLine], image_height: float) -> tuple[list[str], str | None]:
    """Split OCR lines into message bubbles and find the sender.

    Lines in the header (top of the screen), phone chrome such as clocks and
    "Sender can't accept replies", and stray icons are dropped. A vertical gap
    wider than about 1.3 line-heights starts a new message.

    Returns:
        ``(messages, sender)``.
    """
    ordered = sorted(lines, key=lambda line: (line.y, line.x))
    sender = _find_sender(ordered, image_height)
    header_bottom = _header_bottom(ordered, image_height, sender)
    body = [line for line in ordered if not _is_header_noise(line, header_bottom, sender)]
    if not body:
        return [], sender
    line_height = statistics.median(line.height for line in body) or 1.0

    blocks: list[list[OcrLine]] = [[]]
    for line in body:
        if _is_chrome(line.text):
            # A time stamp or label between bubbles ends a message; a stray icon mark
            # (often beside the text, like a notification's "^") is just skipped.
            if len(line.text.strip()) >= 4:
                blocks.append([])
        elif blocks[-1] and line.y - blocks[-1][-1].bottom <= _GAP * line_height:
            blocks[-1].append(line)
        else:
            blocks.append([line])

    messages = []
    for block in blocks:
        kept = [line.text.strip() for line in block if not _is_chrome(line.text)]
        text = fix_ocr_text(" ".join(kept))
        if len(text) >= 15 and any(ch.isdigit() for ch in text):
            messages.append(text)
    return messages, sender


# -- engines ------------------------------------------------------------------------------


def _load_image(image: ImageInput) -> Any:
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - depends on the environment
        raise OcrUnavailable(
            'Reading screenshots needs Pillow. Install it with: pip install "cedikit[ocr]"'
        ) from None
    source = io.BytesIO(image) if isinstance(image, bytes) else image
    return Image.open(source).convert("RGB")


def _windows_engine(img: Any) -> list[OcrLine]:
    """Windows' built-in OCR (Windows 10 and later), via the winrt packages."""
    import asyncio

    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

    limit = OcrEngine.max_image_dimension
    scale = 1.0
    if max(img.size) > limit:
        scale = limit / max(img.size)
        img = img.resize((int(img.width * scale), int(img.height * scale)))
    buffer = io.BytesIO()
    img.save(buffer, "PNG")

    async def recognise() -> list[OcrLine]:
        engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is None:  # pragma: no cover - no OCR language installed
            raise OcrUnavailable("Windows has no OCR language installed (Settings > Language).")
        stream = InMemoryRandomAccessStream()
        writer = DataWriter(stream)
        writer.write_bytes(buffer.getvalue())
        await writer.store_async()
        writer.detach_stream()
        stream.seek(0)
        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()
        result = await engine.recognize_async(bitmap)
        lines = []
        for line in result.lines:
            rects = [word.bounding_rect for word in line.words]
            left = min(r.x for r in rects)
            top = min(r.y for r in rects)
            right = max(r.x + r.width for r in rects)
            bottom = max(r.y + r.height for r in rects)
            lines.append(
                OcrLine(
                    line.text,
                    left / scale,
                    top / scale,
                    (right - left) / scale,
                    (bottom - top) / scale,
                )
            )
        return lines

    # Run on a fresh worker thread. Windows sends OCR's "done" signal back to the
    # calling thread's COM apartment; from a GUI thread (Tkinter) that deadlocks, and
    # asyncio.run() fails where an event loop is already running (Jupyter, Streamlit).
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, recognise()).result(timeout=60)


def _rapid_engine(img: Any) -> list[OcrLine]:  # pragma: no cover - used off Windows
    """RapidOCR (ONNX models, bundled with the package), for Linux and macOS."""
    import numpy
    from rapidocr_onnxruntime import RapidOCR

    result, _elapsed = RapidOCR()(numpy.asarray(img))
    lines = []
    for box, text, _score in result or []:
        xs = [point[0] for point in box]
        ys = [point[1] for point in box]
        lines.append(OcrLine(text, min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)))
    return lines


_BEST_LINE_HEIGHT = 22  # pixels; OCR engines read phone text best around this size


def _readings(img: Any, run: Callable[[Any], list[OcrLine]]) -> list[list[OcrLine]]:
    """Read the image as it is and, if its text is much bigger or smaller than OCR
    likes, again at a better size.

    Phones with large text settings give screenshots whose letters are too big for
    OCR, which then skips words (often the underlined dates and times); tiny text
    has the opposite problem. Neither size wins every time, so both are returned.
    """
    lines = run(img)
    if not lines:
        return [lines]
    height = statistics.median(line.height for line in lines)
    factor = _BEST_LINE_HEIGHT / height if height else 1.0
    if 0.75 <= factor <= 1.35:
        return [lines]
    factor = min(max(factor, 0.35), 2.5)
    resized = img.resize((max(int(img.width * factor), 1), max(int(img.height * factor), 1)))
    rescaled = [
        OcrLine(
            line.text, line.x / factor, line.y / factor, line.width / factor, line.height / factor
        )
        for line in run(resized)
    ]
    return [lines, rescaled]


def _score(messages: list[str], sender: str | None) -> tuple[int, bool, int]:
    """Prefer readings where more messages match a known MoMo format, then a
    recognised sender, then more text."""
    parser = _default_parser()
    parsed = sum(parser.parse(m, sender).ok for m in messages)
    return parsed, sender is not None, sum(len(m) for m in messages)


def available_engine() -> tuple[str, Callable[[Any], list[OcrLine]]] | None:
    """The OCR engine that will be used, or None if none is installed."""
    import importlib.util

    if sys.platform == "win32" and importlib.util.find_spec("winrt.windows.media.ocr"):
        return "Windows OCR", _windows_engine
    if importlib.util.find_spec("rapidocr_onnxruntime"):  # pragma: no cover
        return "RapidOCR", _rapid_engine
    return None  # pragma: no cover - depends on the environment


def read_screenshot(image: ImageInput) -> Screenshot:
    """Read the MoMo messages in a screenshot (a file path or the image bytes).

    Raises:
        OcrUnavailable: If no OCR engine or image library is installed.
    """
    engine = available_engine()
    if engine is None:  # pragma: no cover - depends on the environment
        raise OcrUnavailable(
            'Reading screenshots needs an OCR engine. Install it with: pip install "cedikit[ocr]"'
        )
    name, run = engine
    img = _load_image(image)
    best: Screenshot | None = None
    best_score = (-1, False, -1)
    for lines in _readings(img, run):
        messages, sender = group_messages(lines, img.height)
        score = _score(messages, sender)
        if score > best_score:
            best, best_score = Screenshot(messages, sender, name, lines), score
    assert best is not None
    return best
