"""The ``cedikit`` command-line tool.

Examples::

    cedikit phone clean customers.csv --column phone --output cleaned.csv
    cedikit sms parse inbox.txt --export xlsx
    cedikit fraud check "You have received GHS 500..." --sender 0551234567
"""

from __future__ import annotations

import csv
import sys
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Annotated, Optional

import typer

from cedikit import __version__, fees, fraud, money, phone
from cedikit.exceptions import CedikitError
from cedikit.fees import Kind
from cedikit.ids import ghana_card, gpgps
from cedikit.ledger import Ledger, read_messages
from cedikit.sms.anonymise import anonymise_many

app = typer.Typer(help="Tools for Ghanaian phone numbers, cedi amounts and Mobile Money SMS.")
phone_app = typer.Typer(help="Clean, check and format phone numbers.")
money_app = typer.Typer(help="Parse, format and spell out cedi amounts.")
sms_app = typer.Typer(help="Parse and anonymise Mobile Money SMS.")
fraud_app = typer.Typer(help="Check payment SMS for signs of fraud.")
fees_app = typer.Typer(help="Estimate Mobile Money charges.")
ids_app = typer.Typer(help="Check Ghana Card numbers and digital addresses.")
for sub, name in [
    (phone_app, "phone"),
    (money_app, "money"),
    (sms_app, "sms"),
    (fraud_app, "fraud"),
    (fees_app, "fees"),
    (ids_app, "ids"),
]:
    app.add_typer(sub, name=name)


class ExportFormat(str, Enum):
    csv = "csv"
    xlsx = "xlsx"
    json = "json"


class PhoneStyleOption(str, Enum):
    e164 = "e164"
    local = "local"
    pretty = "pretty"
    international = "international"


KindOption = Enum("KindOption", {k: k for k in Kind.__args__}, type=str)  # type: ignore[misc]


def _fail(message: str) -> typer.Exit:
    typer.secho(message, fg=typer.colors.RED, err=True)
    return typer.Exit(1)


def _version(value: bool) -> None:
    if value:
        typer.echo(f"cedikit {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        Optional[bool],  # noqa: UP045 - typer needs Optional on Python 3.10
        typer.Option("--version", callback=_version, is_eager=True, help="Show the version."),
    ] = None,
) -> None:
    """cedikit: built in Ghana, for Ghana. Everything runs offline."""


# -- phone --------------------------------------------------------------------


@phone_app.command("clean")
def phone_clean(
    input: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="CSV file.")],
    column: Annotated[str, typer.Option(help="Column holding the phone numbers.")] = "phone",
    output: Annotated[Optional[Path], typer.Option(help="Where to write the cleaned CSV.")] = None,  # noqa: UP045
    style: Annotated[PhoneStyleOption, typer.Option(help="Output format.")] = PhoneStyleOption.e164,
) -> None:
    """Normalise a column of phone numbers and report what was fixed or invalid."""
    with input.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        fields = list(reader.fieldnames or [])
    if column not in fields:
        raise _fail(f"No column {column!r}. Columns: {', '.join(fields)}")

    report = phone.clean_column(row[column] for row in rows)
    output = output or input.with_name(f"{input.stem}_cleaned.csv")
    with output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=[*fields, f"{column}_status", f"{column}_note"])
        writer.writeheader()
        for row, result in zip(rows, report.results, strict=True):
            if result.normalised:
                row[column] = phone.format(result.normalised, style.value)
            writer.writerow(
                {**row, f"{column}_status": result.status, f"{column}_note": result.reason or ""}
            )
    typer.echo(str(report))
    for bad in report.invalid[:10]:
        typer.echo(f"  invalid: {bad.original!r} - {bad.reason}")
    if report.invalid_count > 10:
        typer.echo(f"  ... and {report.invalid_count - 10} more (see the _status column)")
    typer.echo(f"Saved {output}")


@phone_app.command("check")
def phone_check(number: str) -> None:
    """Validate one number and show its formats and likely network."""
    try:
        e164 = phone.normalise(number)
    except CedikitError as exc:
        raise _fail(str(exc)) from None
    guess = phone.likely_network(e164)
    typer.echo(f"E.164:         {e164}")
    typer.echo(f"Local:         {phone.format(e164, 'local')}")
    typer.echo(f"International: {phone.format(e164, 'international')}")
    typer.echo(f"Network:       {guess.network} (likely - {guess.note})")


# -- money --------------------------------------------------------------------


@money_app.command("parse")
def money_parse(text: str) -> None:
    """Parse text such as "GH₵1.2k" into an exact amount."""
    try:
        typer.echo(money.parse(text))
    except CedikitError as exc:
        raise _fail(str(exc)) from None


@money_app.command("words")
def money_words(amount: str) -> None:
    """Spell out an amount, as on a cheque."""
    try:
        typer.echo(money.to_words(amount))
    except (CedikitError, ValueError) as exc:
        raise _fail(str(exc)) from None


# -- sms ----------------------------------------------------------------------


@sms_app.command("parse")
def sms_parse(
    input: Annotated[
        Path,
        typer.Argument(
            exists=True, dir_okay=False, help="Messages separated by blank lines, or a CSV."
        ),
    ],
    sender: Annotated[Optional[str], typer.Option(help="Sender ID of the messages.")] = None,  # noqa: UP045
    export: Annotated[Optional[ExportFormat], typer.Option(help="Save the ledger.")] = None,  # noqa: UP045
    output: Annotated[Optional[Path], typer.Option(help="Output file.")] = None,  # noqa: UP045
) -> None:
    """Turn a file of MoMo SMS into a ledger and print a summary."""
    ledger = Ledger.from_messages(read_messages(input), sender).categorise()
    typer.echo(str(ledger.summary()))
    if ledger.notices:
        typer.echo(f"{len(ledger.notices)} notices (e.g. airtime received) were not counted.")
    if ledger.unrecognised:
        typer.secho(
            f"{len(ledger.unrecognised)} messages were not recognised.", fg=typer.colors.YELLOW
        )
    for gap in ledger.balance_gaps():
        typer.secho(
            f"Balance gap before {gap.after.transaction_id or 'a transaction'}: expected "
            f"{money.format(gap.expected)}, message says {money.format(gap.actual)} "
            "(a message may be missing).",
            fg=typer.colors.YELLOW,
        )
    if export or output:
        fmt = export.value if export else (output.suffix.lstrip(".") if output else "csv")
        path = output or input.with_name(f"{input.stem}_ledger.{fmt}")
        try:
            ledger.export(path, fmt)  # type: ignore[arg-type]  # validated by export()
        except (ValueError, ImportError) as exc:
            raise _fail(str(exc)) from None
        typer.echo(f"Saved {path}")


@sms_app.command("anonymise")
def sms_anonymise(
    input: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    seed: Annotated[Optional[int], typer.Option(help="Make the output repeatable.")] = None,  # noqa: UP045
) -> None:
    """Replace names, numbers, IDs, amounts and dates (keeps balances consistent)."""
    messages = [(m["text"], m.get("sender") or None) for m in read_messages(input)]
    for result in anonymise_many(messages, seed=seed):
        if result.needs_review:
            typer.secho("# CHECK BY HAND: " + " ".join(result.notes), fg=typer.colors.YELLOW)
        typer.echo(result.text + "\n")


# -- fraud --------------------------------------------------------------------


@fraud_app.command("check")
def fraud_check(
    message: Annotated[str, typer.Argument(help="The SMS text (use - to read from stdin).")],
    sender: Annotated[Optional[str], typer.Option(help="Who sent it.")] = None,  # noqa: UP045
) -> None:
    """Rate how likely a payment SMS is to be fake, and explain why."""
    text = sys.stdin.read() if message == "-" else message
    report = fraud.check(text, sender=sender)
    colour = {"LOW": typer.colors.GREEN, "MEDIUM": typer.colors.YELLOW, "HIGH": typer.colors.RED}
    lines = str(report).splitlines()
    typer.secho(lines[0], fg=colour[report.risk], bold=True)
    typer.echo("\n".join(lines[1:]))
    if sender is None:
        typer.echo("Tip: pass --sender; fake alerts almost always come from personal numbers.")


# -- fees ---------------------------------------------------------------------


@fees_app.command("estimate")
def fees_estimate(
    network: str,
    kind: Annotated[KindOption, typer.Argument()],
    amount: str,
    on: Annotated[
        Optional[str],  # noqa: UP045
        typer.Option(help="Date YYYY-MM-DD (default today)."),
    ] = None,
) -> None:
    """Estimate the fee and E-Levy for a transaction."""
    try:
        day = date.fromisoformat(on) if on else None
        typer.echo(str(fees.estimate(network, kind.value, amount, day)))
    except (CedikitError, ValueError) as exc:
        raise _fail(str(exc)) from None


# -- ids ----------------------------------------------------------------------


@ids_app.command("check")
def ids_check(value: str) -> None:
    """Check a Ghana Card number or GhanaPostGPS address (format only)."""
    if ghana_card.is_valid_format(value):
        typer.echo(
            f"Ghana Card number, valid format: {ghana_card.normalise(value)} "
            f"({ghana_card.card_type(value)})"
        )
    elif gpgps.is_valid_format(value):
        address = gpgps.parse(value)
        place = ", ".join(p for p in (address.district, address.region) if p)
        typer.echo(f"GhanaPostGPS address, valid format: {address.code} ({place})")
    else:
        raise _fail(f"{value!r} is neither a Ghana Card number nor a GhanaPostGPS address.")
    typer.echo("Format check only: this does not confirm that it exists.")


# -- apps ---------------------------------------------------------------------


@app.command("app")
def open_desktop_app() -> None:
    """Open the desktop app (windows and buttons, no typing commands)."""
    try:
        from cedikit.app.desktop import main as desktop_main
    except ImportError as exc:  # e.g. Linux without the python3-tk package
        raise _fail(f"The desktop app needs Tkinter, which isn't available: {exc}") from None
    desktop_main([])


@app.command("web")
def open_web_app(
    port: Annotated[int, typer.Option(help="Port to serve on.")] = 8501,
) -> None:
    """Open the web app in your browser (runs on this computer only)."""
    import importlib.util
    import subprocess

    if importlib.util.find_spec("streamlit") is None:
        raise _fail('The web app needs Streamlit. Install it with: pip install "cedikit[web]"')
    script = Path(__file__).parent / "app" / "web.py"
    typer.echo(f"Starting cedikit web app at http://localhost:{port} (Ctrl+C to stop)")
    command = [
        sys.executable, "-m", "streamlit", "run", str(script),
        "--server.port", str(port),
        "--server.address", "localhost",
        "--browser.gatherUsageStats", "false",
        "--client.toolbarMode", "minimal",
    ]  # fmt: skip
    raise typer.Exit(subprocess.call(command))


if __name__ == "__main__":  # pragma: no cover
    app()
