"""Display-ready helpers shared by the cedikit desktop and web apps.

Everything here is plain Python (no GUI code), so both apps show exactly the
same results and the logic is easy to test.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from cedikit import fees, money
from cedikit.fraud import FraudReport
from cedikit.ids import ghana_card, gpgps
from cedikit.ledger import Ledger, split_messages
from cedikit.ocr import Screenshot
from cedikit.phone import CleanReport
from cedikit.sms.models import TransactionType

__all__ = [
    "EXAMPLES",
    "FEE_KINDS",
    "RISK_STYLES",
    "SAMPLE_MESSAGES",
    "SAMPLE_PHONES",
    "TRANSACTION_COLUMNS",
    "IdResult",
    "RiskStyle",
    "check_id",
    "describe",
    "estimate_fee",
    "ledger_notes",
    "network_name",
    "phone_rows",
    "sample_screenshot",
    "screenshot_note",
    "summary_items",
    "transaction_rows",
]


@dataclass(frozen=True)
class RiskStyle:
    icon: str
    colour: str
    headline: str
    advice: str


RISK_STYLES = {
    "LOW": RiskStyle("🟢", "#006B3F", "Looks safe", "No warning signs found."),
    "MEDIUM": RiskStyle(
        "🟡", "#B7791F", "Be careful", "Some warning signs. Check before you trust it."
    ),
    "HIGH": RiskStyle("🔴", "#CE1126", "Very likely fake", "Do NOT release goods or send money."),
}

# Anonymised examples, so people can try the checker without their own messages.
EXAMPLES: dict[str, tuple[str, str]] = {
    "Genuine MTN payment": (
        "Payment received for GHS 50.00 from KOFI MENSAH Current Balance: GHS 80.00 . "
        "Available Balance: GHS 80.00. Reference: Rent. Transaction ID: 51234567890. "
        "TRANSACTION FEE: 0.00",
        "MobileMoney",
    ),
    "Fake cash-in": (
        "Cash In  for\nGHS150.00 from\nAKOSUA MANSA OVER THE COUNTER MEDICINE SELLE. "
        "Balance 640.35\nAvaliable balan 640.35\nTransaction\nID: 00581234567:",
        "+233591234567",
    ),
    "Fake 'account blocked'": (
        "SORRY YOU HAVE BEING BLOCKED BY TOO MANY AGENT REPORT, DO NOT TRY YOUR PIN THANK YOU...",
        "+233591234567",
    ),
}

# Made-up messages in the real MTN formats, for the "Try with samples" buttons.
SAMPLE_MESSAGES = "\n\n".join(
    [
        "Payment received for GHS 120.00 from KWESI APPIAH Current Balance: GHS 320.00 . "
        "Available Balance: GHS 320.00. Reference: Rice. Transaction ID: 51234567890. "
        "TRANSACTION FEE: 0.00",
        "Payment received for GHS 45.00 from AMA SERWAA Current Balance: GHS 365.00 . "
        "Available Balance: GHS 365.00. Reference: Oil. Transaction ID: 51234569911. "
        "TRANSACTION FEE: 0.00",
        "Payment for GHS200.00 to KUMASI WHOLESALE PROVISIONS .Current Balance: GHS 165.00. "
        "Transaction Id: 51234570002. Fee charged: GHS0.00,Tax Charged 0.",
        "Cash Out made for GHS100.00 to ADOM MOBILE MONEY ENTERPRISE . Current Balance: "
        "GHS64.00 Financial Transaction Id: 51234571234. Cash-out fee is charged automatically "
        "from your MTN MoMo wallet. Fee charged: GHS1.00.",
        "Payment for GHS50.00 to Sika Quick Loan .Current Balance: GHS 14.00. "
        "Transaction Id: 51234572345. Fee charged: GHS0.00,Tax Charged 0.",
        "Payment received for GHS 80.00 from KWESI APPIAH Current Balance: GHS 94.00 . "
        "Available Balance: GHS 94.00. Reference: Sugar. Transaction ID: 51234573456. "
        "TRANSACTION FEE: 0.00",
    ]
)


def screenshot_note(shot: Screenshot, pictures: int = 1) -> str:
    """What was read from screenshot(s), and a reminder to check it."""
    count = len(shot.messages)
    found = f"Read {count} message{'s' if count != 1 else ''}"
    if pictures > 1:
        found += f" from {pictures} pictures"
    if count > 1 and pictures == 1:
        found += " (showing the newest; pick another above)"
    sender = (
        f"Sender read from the picture: {shot.sender}. Check that it's right."
        if shot.sender
        else "The sender couldn't be read from the picture: please type it in."
    )
    return (
        f"{found}. {sender} Compare the text with your screenshot, because reading "
        "pictures isn't perfect."
    )


def sample_screenshot() -> bytes:
    """A made-up phone screenshot (PNG) with two MoMo messages, for demos and self-tests.

    Drawn with Pillow, so it needs the ``ocr`` extra.
    """
    import io
    import textwrap

    from PIL import Image, ImageDraw, ImageFont

    def font(size: int) -> Any:
        for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf", "Helvetica.ttc"):
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                continue
        return ImageFont.load_default(size=size)  # pragma: no cover

    width, height = 720, 1280
    img = Image.new("RGB", (width, height), "#ffffff")
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, width, 150], fill="#f3f4f6")
    draw.text((32, 18), "10:24", font=font(26), fill="#111111")
    draw.text((width // 2, 95), "MobileMoney", font=font(34), fill="#111111", anchor="mm")
    body, line_height, y = font(28), 40, 200
    messages = split_messages(SAMPLE_MESSAGES)[:2]
    for message in messages:
        lines = textwrap.wrap(message, 38)
        box_height = len(lines) * line_height + 36
        draw.rounded_rectangle([24, y, width - 90, y + box_height], radius=28, fill="#e5e7eb")
        for i, line in enumerate(lines):
            draw.text((48, y + 18 + i * line_height), line, font=body, fill="#111111")
        y += box_height + 70
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


SAMPLE_PHONES = """024 412 3456
+233 50 123 4567
233271234567
(055) 987-6543
0244123456
12345
021 123 4567
"""

NETWORK_NAMES = {"MTN": "MTN", "TELECEL": "Telecel", "AT": "AT"}


def network_name(code: str | None) -> str:
    """How a network code is shown to people, e.g. TELECEL -> Telecel."""
    return NETWORK_NAMES.get(code or "", (code or "").title())


TYPE_LABELS = {
    TransactionType.RECEIVED: "Money received",
    TransactionType.SENT: "Money sent",
    TransactionType.CASH_IN: "Cash deposit",
    TransactionType.CASH_OUT: "Cash withdrawal",
    TransactionType.MERCHANT: "Payment",
    TransactionType.AIRTIME: "Airtime / data",
    TransactionType.BILL: "Bill payment",
    TransactionType.REVERSAL: "Reversal",
}

FEE_KINDS: dict[str, str] = {
    "send_same_network": "Send money (same network)",
    "send_other_network": "Send money (other network)",
    "cash_out": "Cash out (withdraw)",
    "cash_in": "Cash in (deposit)",
    "receive": "Receive money",
    "airtime": "Buy airtime",
    "merchant": "Pay a shop / merchant",
}

TRANSACTION_COLUMNS = [
    "Date",
    "Network",
    "What",
    "In",
    "Out",
    "Fee",
    "Who",
    "Balance",
    "Category",
]


def _cedis(value: Decimal | None) -> str:
    return money.format(value) if value is not None else ""


def transaction_rows(ledger: Ledger) -> list[dict[str, str]]:
    """One row per transaction, with friendly labels, for a table."""
    rows = []
    for entry in ledger.entries:
        t = entry.transaction
        cp = t.counterparty
        who = (cp.name or cp.phone or "") if cp else ""
        incoming = t.type.direction == "in"
        rows.append(
            {
                "Date": f"{t.timestamp:%d %b %Y %H:%M}" if t.timestamp else "",
                "Network": network_name(t.network),
                "What": TYPE_LABELS[t.type],
                "In": _cedis(t.amount) if incoming else "",
                "Out": "" if incoming else _cedis(t.amount),
                "Fee": _cedis(t.fee) if t.fee else "",
                "Who": who,
                "Balance": _cedis(t.balance),
                "Category": entry.category or "",
            }
        )
    return rows


def summary_items(ledger: Ledger) -> list[tuple[str, str]]:
    """Label/value pairs summarising a ledger."""
    s = ledger.summary()
    items = [
        ("Transactions", str(s.transactions)),
        ("Money in", money.format(s.total_in)),
        ("Money out", money.format(s.total_out)),
        ("Fees paid", money.format(s.fees)),
        ("Taxes paid", money.format(s.taxes)),
        ("Net (in - out - fees - taxes)", money.format(s.net)),
    ]
    if s.first and s.last:
        items.append(("Period", f"{s.first:%d %b %Y} to {s.last:%d %b %Y}"))
    items += [
        (f"Last {network_name(net)} balance", money.format(bal))
        for net, bal in s.closing_balances.items()
    ]
    return items


def ledger_notes(ledger: Ledger) -> list[str]:
    """Things the user should know about how the ledger was built."""
    notes = []
    if ledger.unrecognised:
        notes.append(
            f"{len(ledger.unrecognised)} message(s) were not recognised as MoMo transactions "
            "and were left out."
        )
    if ledger.notices:
        notes.append(
            f"{len(ledger.notices)} notice(s), such as 'you have received airtime', repeat another "
            "transaction and were not counted twice."
        )
    if ledger.duplicates:
        notes.append(f"{ledger.duplicates} duplicate message(s) were ignored.")
    undated = ledger.summary().undated
    if undated:
        notes.append(f"{undated} transaction(s) have no date (MTN messages don't include one).")
    for gap in ledger.balance_gaps():
        notes.append(
            f"Balance jump before {gap.after.transaction_id or 'a transaction'}: expected "
            f"{money.format(gap.expected)}, message says {money.format(gap.actual)}. "
            "A message may be missing (e.g. an automatic loan deduction)."
        )
    return notes


def phone_rows(report: CleanReport) -> list[dict[str, str]]:
    """One row per number from :func:`cedikit.phone.clean_column`."""
    from cedikit import phone

    rows = []
    for r in report.results:
        network = phone.likely_network(r.normalised).network if r.normalised else None
        rows.append(
            {
                "Original": "" if r.original is None else str(r.original),
                "Cleaned": r.normalised or "",
                "Network": network_name(network),
                "Status": {"valid": "OK", "fixed": "Fixed", "invalid": "Invalid"}[r.status],
                "Note": r.reason or "",
            }
        )
    return rows


def estimate_fee(network: str, kind_label: str, amount: str, on: date | None) -> str:
    """A fee estimate as readable text; raises ValueError for bad input."""
    kind = next(k for k, label in FEE_KINDS.items() if label == kind_label)
    return str(fees.estimate(network, kind, amount, on))  # type: ignore[arg-type]


@dataclass(frozen=True)
class IdResult:
    ok: bool
    kind: str
    message: str


def check_id(value: str) -> IdResult:
    """Check a Ghana Card number or GhanaPostGPS address."""
    value = value.strip()
    if ghana_card.is_valid_format(value):
        number = ghana_card.normalise(value)
        return IdResult(
            True,
            "Ghana Card",
            f"{number} is correctly written ({ghana_card.card_type(value)} card). "
            f"Masked for sharing: {ghana_card.mask(value)}.",
        )
    if gpgps.is_valid_format(value):
        address = gpgps.parse(value)
        place = ", ".join(p for p in (address.district, address.region) if p)
        return IdResult(True, "Digital address", f"{address.code} is correctly written: {place}.")
    return IdResult(
        False,
        "Unknown",
        "This is not a correctly written Ghana Card number (e.g. GHA-123456789-0) "
        "or GhanaPostGPS address (e.g. AK-039-5028).",
    )


def describe(report: FraudReport) -> RiskStyle:
    """The colour, icon and headline for a fraud report."""
    return RISK_STYLES[report.risk]
