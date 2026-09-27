"""A web (HTTP/JSON) API for cedikit, so apps in any language can use it.

Start it with ``cedikit api`` (needs ``pip install "cedikit[api]"``), then open
http://127.0.0.1:8000/docs for interactive documentation.

Design notes:

* **Money is always a string** in JSON (``"1200.50"``), never a number, so no client
  language can introduce floating-point errors.
* **Nothing is stored or logged.** Each request is processed in memory and forgotten.
* **Optional API key:** set ``CEDIKIT_API_KEY`` and every request must send it in the
  ``X-API-Key`` header. Use this if you host the API anywhere other than your own
  computer.
* ``CEDIKIT_API_CORS`` sets which websites may call the API from a browser
  (comma-separated origins; default ``*``).
"""

from __future__ import annotations

import os
import secrets
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from cedikit import __version__, fees, fraud, money, ocr, phone, sms
from cedikit.app import common
from cedikit.exceptions import CedikitError, InvalidPhoneNumber
from cedikit.fees import Kind
from cedikit.ids import ghana_card, gpgps
from cedikit.ledger import Ledger
from cedikit.sms.models import Transaction

__all__ = ["app", "create_app"]

MAX_TEXT = 5_000  # characters in one message
MAX_ITEMS = 5_000  # messages or numbers in one request
MAX_IMAGE = 10 * 1024 * 1024  # bytes

Text = Annotated[str, Field(min_length=1, max_length=MAX_TEXT)]
PhoneStyle = Literal["e164", "local", "pretty", "international"]


def _cedis(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


# -- request and response models ---------------------------------------------------------


class PhoneIn(BaseModel):
    number: Annotated[str, Field(max_length=40, examples=["024 412 3456"])]
    style: PhoneStyle = "e164"


class PhoneOut(BaseModel):
    input: str
    valid: bool
    e164: str | None = Field(default=None, examples=["+233244123456"])
    formatted: str | None = None
    network: str | None = Field(default=None, description="Likely network; numbers can be ported.")
    masked: str | None = None
    reason: str | None = Field(default=None, description="Why the number is invalid.")


class PhoneCleanIn(BaseModel):
    numbers: Annotated[list[str], Field(max_length=MAX_ITEMS)]


class PhoneCleanRow(BaseModel):
    original: str
    e164: str | None
    status: Literal["valid", "fixed", "invalid"]
    network: str | None
    reason: str | None


class PhoneCleanOut(BaseModel):
    total: int
    valid: int
    fixed: int
    invalid: int
    results: list[PhoneCleanRow]


class MoneyIn(BaseModel):
    text: Annotated[str, Field(max_length=100, examples=["GH₵1.2k"])]


class MoneyOut(BaseModel):
    amount: str = Field(examples=["1200.00"], description="Exact amount, as a string.")
    formatted: str = Field(examples=["GH₵ 1,200.00"])
    formatted_code: str = Field(examples=["GHS 1,200.00"])
    words: str


class CounterpartyOut(BaseModel):
    name: str | None
    phone: str | None
    network: str | None


class TransactionOut(BaseModel):
    network: str
    type: str
    direction: Literal["in", "out"]
    amount: str
    fee: str | None
    tax: str | None
    balance: str | None
    available_balance: str | None
    counterparty: CounterpartyOut | None
    transaction_id: str | None
    reference: str | None
    timestamp: datetime | None
    affects_wallet: bool
    confidence: float
    needs_review: bool
    template: str


def _transaction(tx: Transaction) -> TransactionOut:
    cp = tx.counterparty
    return TransactionOut(
        network=tx.network,
        type=tx.type.value,
        direction=tx.type.direction,
        amount=str(tx.amount),
        fee=_cedis(tx.fee),
        tax=_cedis(tx.tax),
        balance=_cedis(tx.balance),
        available_balance=_cedis(tx.available_balance),
        counterparty=CounterpartyOut(name=cp.name, phone=cp.phone, network=cp.network)
        if cp
        else None,
        transaction_id=tx.transaction_id,
        reference=tx.reference,
        timestamp=tx.timestamp,
        affects_wallet=tx.affects_wallet,
        confidence=tx.confidence,
        needs_review=tx.needs_review,
        template=tx.template,
    )


class MessageIn(BaseModel):
    text: Text
    sender: str | None = Field(default=None, max_length=40, examples=["MobileMoney"])
    received_at: datetime | None = Field(
        default=None, description="When the SMS arrived (used when the message has no date)."
    )


class ParseOut(BaseModel):
    status: Literal["parsed", "unrecognised"]
    transaction: TransactionOut | None


class FraudIn(BaseModel):
    text: Text
    sender: str | None = Field(
        default=None, max_length=40, description="Who sent it. Strongly recommended.",
        examples=["+233591234567"],
    )  # fmt: skip
    history: Annotated[list[MessageIn], Field(max_length=MAX_ITEMS)] = Field(
        default_factory=list,
        description="Earlier genuine messages from the same wallet, oldest first.",
    )


class FraudOut(BaseModel):
    risk: Literal["LOW", "MEDIUM", "HIGH"]
    score: float
    headline: str
    reasons: list[str]
    checks: dict[str, bool]
    advice: str


def _fraud_out(report: fraud.FraudReport) -> FraudOut:
    return FraudOut(
        risk=report.risk,
        score=report.score,
        headline=common.describe(report).headline,
        reasons=report.reasons,
        checks=report.checks,
        advice=report.advice,
    )


class LedgerIn(BaseModel):
    messages: Annotated[list[str | MessageIn], Field(min_length=1, max_length=MAX_ITEMS)]
    sender: str | None = Field(default=None, max_length=40, examples=["MobileMoney"])
    categorise: bool = True


class LedgerSummaryOut(BaseModel):
    transactions: int
    total_in: str
    total_out: str
    fees: str
    taxes: str
    net: str
    first: datetime | None
    last: datetime | None
    closing_balances: dict[str, str]


class LedgerTransactionOut(TransactionOut):
    category: str | None


class LedgerOut(BaseModel):
    summary: LedgerSummaryOut
    transactions: list[LedgerTransactionOut]
    category_totals: dict[str, str]
    notes: list[str] = Field(description="Unrecognised messages, balance gaps, and so on.")
    unrecognised: int
    notices: int
    duplicates: int


class FeeIn(BaseModel):
    network: Annotated[str, Field(max_length=20, examples=["MTN"], description="MTN or TELECEL")]
    kind: Kind
    amount: Annotated[str, Field(max_length=40, examples=["500"])]
    on: date | None = Field(default=None, description="Transaction date (default: today).")


class FeeOut(BaseModel):
    network: str
    kind: str
    amount: str
    on: date
    fee: str | None = Field(description="null when unknown")
    tax: str | None = Field(description="null when unknown")
    total: str | None
    known: bool
    basis: list[str] = Field(description="Where each number comes from.")
    is_estimate: bool


class IdIn(BaseModel):
    value: Annotated[str, Field(max_length=40, examples=["GHA-123456789-0"])]


class IdOut(BaseModel):
    valid: bool
    kind: Literal["ghana_card", "digital_address", "unknown"]
    normalised: str | None
    card_type: str | None = None
    masked: str | None = None
    region: str | None = None
    district: str | None = None
    message: str


class ScreenshotMessageOut(BaseModel):
    text: str
    parsed: ParseOut
    fraud: FraudOut | None


class ScreenshotOut(BaseModel):
    engine: str
    sender: str | None
    messages: list[ScreenshotMessageOut]


# -- the app ------------------------------------------------------------------------------


def create_app(api_key: str | None = None, cors_origins: list[str] | None = None) -> FastAPI:
    """Build the API. ``api_key`` and ``cors_origins`` default to the
    ``CEDIKIT_API_KEY`` and ``CEDIKIT_API_CORS`` environment variables;
    an empty ``api_key`` turns the key check off."""
    key = (api_key if api_key is not None else os.environ.get("CEDIKIT_API_KEY")) or None
    origins = cors_origins or [
        o.strip() for o in os.environ.get("CEDIKIT_API_CORS", "*").split(",") if o.strip()
    ]

    def check_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
        if key is not None and not (x_api_key and secrets.compare_digest(x_api_key, key)):
            raise HTTPException(401, "Missing or wrong X-API-Key header.")

    app = FastAPI(
        title="cedikit API",
        version=__version__,
        description=(
            "Ghanaian phone numbers, cedi amounts and Mobile Money messages as a web API. "
            "Money is always a string, never a number. Nothing you send is stored.\n\n"
            "Fraud results are risk indicators, not guarantees: always confirm payments "
            "in the official MoMo app."
        ),
        contact={"name": "cedikit", "url": "https://github.com/brainiacweb-tech/cedikit"},
        license_info={"name": "MIT"},
    )
    app.add_middleware(
        CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )  # fmt: skip

    @app.exception_handler(CedikitError)
    @app.exception_handler(ValueError)
    async def bad_input(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    guarded = [Depends(check_key)]

    @app.get("/", tags=["about"])
    def about() -> dict[str, Any]:
        """What this API is, and where to start."""
        return {
            "name": "cedikit API",
            "version": __version__,
            "docs": "/docs",
            "endpoints": sorted(
                {route.path for route in app.routes if route.path.startswith("/v1/")}  # type: ignore[attr-defined]
            ),
        }

    @app.get("/health", tags=["about"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # phone ------------------------------------------------------------------------------

    @app.post("/v1/phone/check", tags=["phone"], dependencies=guarded)
    def phone_check(body: PhoneIn) -> PhoneOut:
        """Validate one Ghanaian mobile number, format it and guess its network."""
        try:
            e164 = phone.normalise(body.number)
        except InvalidPhoneNumber as exc:
            return PhoneOut(input=body.number, valid=False, reason=exc.reason)
        return PhoneOut(
            input=body.number,
            valid=True,
            e164=e164,
            formatted=phone.format(e164, body.style),
            network=phone.likely_network(e164).network,
            masked=phone.mask(e164),
        )

    @app.post("/v1/phone/clean", tags=["phone"], dependencies=guarded)
    def phone_clean(body: PhoneCleanIn) -> PhoneCleanOut:
        """Clean a whole list of numbers (e.g. a customer list)."""
        report = phone.clean_column(body.numbers)
        return PhoneCleanOut(
            total=len(report.results),
            valid=report.valid_count,
            fixed=report.fixed_count,
            invalid=report.invalid_count,
            results=[
                PhoneCleanRow(
                    original="" if r.original is None else str(r.original),
                    e164=r.normalised,
                    status=r.status,
                    network=phone.likely_network(r.normalised).network if r.normalised else None,
                    reason=r.reason,
                )
                for r in report.results
            ],
        )

    # money ------------------------------------------------------------------------------

    @app.post("/v1/money/parse", tags=["money"], dependencies=guarded)
    def money_parse(body: MoneyIn) -> MoneyOut:
        """Read an amount such as "GH₵1.2k", "GHS 1,200.50" or "50p" exactly."""
        value = money.parse(body.text)
        return MoneyOut(
            amount=str(value),
            formatted=money.format(value),
            formatted_code=money.format(value, "code"),
            words=money.to_words(value),
        )

    # sms ------------------------------------------------------------------------------

    @app.post("/v1/sms/parse", tags=["sms"], dependencies=guarded)
    def sms_parse(body: MessageIn) -> ParseOut:
        """Turn one MTN MoMo or Telecel Cash SMS into structured data."""
        result = sms.parse(body.text, sender=body.sender, received_at=body.received_at)
        return ParseOut(
            status=result.status,
            transaction=_transaction(result.transaction) if result.transaction else None,
        )

    # fraud ------------------------------------------------------------------------------

    @app.post("/v1/fraud/check", tags=["fraud"], dependencies=guarded)
    def fraud_check(body: FraudIn) -> FraudOut:
        """Rate how likely a payment SMS is to be fake, with reasons."""
        history = [
            sms.parse(m.text, sender=m.sender or body.sender, received_at=m.received_at)
            for m in body.history
        ]
        return _fraud_out(fraud.check(body.text, sender=body.sender, history=history))

    # ledger -----------------------------------------------------------------------------

    @app.post("/v1/ledger", tags=["ledger"], dependencies=guarded)
    def ledger(body: LedgerIn) -> LedgerOut:
        """Turn many MoMo messages into an account book: totals, categories, gaps."""
        items = [m if isinstance(m, str) else m.model_dump() for m in body.messages]
        book = Ledger.from_messages(items, sender=body.sender)
        if body.categorise:
            book = book.categorise()
        s = book.summary()
        return LedgerOut(
            summary=LedgerSummaryOut(
                transactions=s.transactions,
                total_in=str(s.total_in),
                total_out=str(s.total_out),
                fees=str(s.fees),
                taxes=str(s.taxes),
                net=str(s.net),
                first=s.first,
                last=s.last,
                closing_balances={k: str(v) for k, v in s.closing_balances.items()},
            ),
            transactions=[
                LedgerTransactionOut(
                    **_transaction(e.transaction).model_dump(), category=e.category
                )
                for e in book.entries
            ],
            category_totals={k: str(v) for k, v in book.category_totals().items()}
            if body.categorise
            else {},
            notes=common.ledger_notes(book),
            unrecognised=len(book.unrecognised),
            notices=len(book.notices),
            duplicates=book.duplicates,
        )

    # fees -------------------------------------------------------------------------------

    @app.post("/v1/fees/estimate", tags=["fees"], dependencies=guarded)
    def fee_estimate(body: FeeIn) -> FeeOut:
        """Estimate a MoMo fee and E-Levy. Unknown values are null, never guessed."""
        e = fees.estimate(body.network, body.kind, body.amount, body.on)
        return FeeOut(
            network=e.network,
            kind=e.kind,
            amount=str(e.amount),
            on=e.on,
            fee=_cedis(e.fee),
            tax=_cedis(e.tax),
            total=_cedis(e.total),
            known=e.known,
            basis=e.basis,
            is_estimate=e.is_estimate,
        )

    # ids --------------------------------------------------------------------------------

    @app.post("/v1/ids/check", tags=["ids"], dependencies=guarded)
    def id_check(body: IdIn) -> IdOut:
        """Check a Ghana Card number or GhanaPostGPS address is written correctly."""
        outcome = common.check_id(body.value)
        if ghana_card.is_valid_format(body.value):
            return IdOut(
                valid=True,
                kind="ghana_card",
                normalised=ghana_card.normalise(body.value),
                card_type=ghana_card.card_type(body.value),
                masked=ghana_card.mask(body.value),
                message=outcome.message,
            )
        if gpgps.is_valid_format(body.value):
            address = gpgps.parse(body.value)
            return IdOut(
                valid=True,
                kind="digital_address",
                normalised=address.code,
                region=address.region,
                district=address.district,
                message=outcome.message,
            )
        return IdOut(valid=False, kind="unknown", normalised=None, message=outcome.message)

    # screenshots ------------------------------------------------------------------------

    @app.post("/v1/screenshot", tags=["screenshot"], dependencies=guarded)
    def screenshot(
        image: Annotated[UploadFile, File(description="PNG, JPG or WEBP screenshot, max 10 MB")],
        check: bool = True,
    ) -> ScreenshotOut:
        """Read MoMo messages (and the sender) from a screenshot, and check each one."""
        data = image.file.read(MAX_IMAGE + 1)
        if len(data) > MAX_IMAGE:
            raise HTTPException(413, "Image too large (max 10 MB).")
        try:
            shot = ocr.read_screenshot(data)
        except ocr.OcrUnavailable as exc:
            raise HTTPException(501, str(exc)) from None
        except (OSError, ValueError):
            raise HTTPException(
                422, "Could not read that picture. Send a PNG, JPG or WEBP screenshot."
            ) from None
        out = []
        for text in shot.messages:
            result = sms.parse(text, sender=shot.sender)
            out.append(
                ScreenshotMessageOut(
                    text=text,
                    parsed=ParseOut(
                        status=result.status,
                        transaction=_transaction(result.transaction)
                        if result.transaction
                        else None,
                    ),
                    fraud=_fraud_out(fraud.check(text, sender=shot.sender)) if check else None,
                )
            )
        return ScreenshotOut(engine=shot.engine, sender=shot.sender, messages=out)

    return app


app = create_app()
