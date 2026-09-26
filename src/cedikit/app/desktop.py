"""The cedikit desktop app (Tkinter): a window with tabs for non-programmers.

Start it with ``cedikit app``, ``cedikit-app`` or ``python -m cedikit.app.desktop``.
Everything runs on this computer; nothing is sent online.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import sys
import tempfile
import time
import tkinter as tk
import webbrowser
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from cedikit import __version__, fraud, money, phone
from cedikit.app import common
from cedikit.exceptions import CedikitError
from cedikit.ledger import Ledger, read_messages, split_messages

__all__ = ["CedikitApp", "main"]

GREEN, GOLD, RED, INK = "#006B3F", "#FCD116", "#CE1126", "#1f2937"
MUTED, PAPER, CARD = "#6b7280", "#f7f7f5", "#ffffff"
FONT = "Segoe UI" if sys.platform == "win32" else "Helvetica"
DOCS = "https://cedikit.readthedocs.io/"
_SCALE = 1.0  # screen scaling (e.g. 1.5 at 150%); set when the window is created


def px(value: int) -> int:
    """Scale a size in pixels for high-resolution screens."""
    return round(value * _SCALE)


REPO = "https://github.com/brainiacweb-tech/cedikit"


# -- small widget helpers ---------------------------------------------------------------


def _text_box(parent: tk.Misc, height: int) -> tk.Text:
    box = tk.Text(
        parent,
        height=height,
        wrap="word",
        font=(FONT, 10),
        relief="solid",
        borderwidth=1,
        padx=8,
        pady=6,
        undo=True,
    )
    return box


def _get(box: tk.Text) -> str:
    return box.get("1.0", "end").strip()


def _set(box: tk.Text, text: str, readonly: bool = False) -> None:
    box.configure(state="normal")
    box.delete("1.0", "end")
    box.insert("1.0", text)
    if readonly:
        box.configure(state="disabled")


def _table(parent: tk.Misc, columns: list[str], widths: dict[str, int]) -> ttk.Treeview:
    frame = ttk.Frame(parent)
    frame.pack(fill="both", expand=True, pady=(8, 0))
    tree = ttk.Treeview(frame, columns=columns, show="headings", height=10)
    for col in columns:
        tree.heading(col, text=col)
        tree.column(col, width=px(widths.get(col, 110)), anchor="w", stretch=True)
    ybar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    xbar = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
    tree.grid(row=0, column=0, sticky="nsew")
    ybar.grid(row=0, column=1, sticky="ns")
    xbar.grid(row=1, column=0, sticky="ew")
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    tree.tag_configure("odd", background="#f3f4f1")
    tree.tag_configure("bad", foreground=RED)
    return tree


def _fill(tree: ttk.Treeview, rows: list[dict[str, str]], bad: str | None = None) -> None:
    tree.delete(*tree.get_children())
    columns = tree["columns"]
    for i, row in enumerate(rows):
        tags = ["odd"] if i % 2 else []
        if bad and row.get("Status") == bad:
            tags.append("bad")
        tree.insert("", "end", values=[row.get(c, "") for c in columns], tags=tags)


def _hint(parent: tk.Misc, text: str) -> ttk.Label:
    label = ttk.Label(parent, text=text, style="Hint.TLabel", wraplength=px(880), justify="left")
    label.pack(anchor="w", pady=(0, 6))
    return label


# -- tabs -------------------------------------------------------------------------------


class CheckTab(ttk.Frame):
    """Is this payment message real or fake?"""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, padding=16)
        ttk.Label(self, text="Is this payment message real?", style="Title.TLabel").pack(anchor="w")
        _hint(
            self,
            "Paste the MoMo message you received and who it came from. cedikit looks for the "
            "warning signs of a fake alert and explains what it finds.",
        )
        self.message = _text_box(self, 6)
        self.message.pack(fill="x")

        row = ttk.Frame(self)
        row.pack(fill="x", pady=8)
        ttk.Label(row, text="Sent by (name or number shown on your phone):").pack(side="left")
        self.sender = ttk.Entry(row, width=22)
        self.sender.pack(side="left", padx=(6, 16))
        ttk.Button(row, text="Check message", style="Accent.TButton", command=self.check).pack(
            side="left"
        )
        self.example = ttk.Combobox(row, values=list(common.EXAMPLES), state="readonly", width=24)
        self.example.set("Try an example...")
        self.example.bind("<<ComboboxSelected>>", self._load_example)
        self.example.pack(side="right")

        self.verdict = tk.Label(
            self, text="", font=(FONT, 16, "bold"), fg="white", bg=PAPER, anchor="w", padx=14,
            pady=10,
        )  # fmt: skip
        self.verdict.pack(fill="x", pady=(8, 0))
        self.details = _text_box(self, 9)
        self.details.configure(background=CARD, relief="flat")
        self.details.pack(fill="both", expand=True)
        _set(self.details, "The result will appear here.", readonly=True)

    def _load_example(self, _event: object = None) -> None:
        text, sender = common.EXAMPLES[self.example.get()]
        _set(self.message, text)
        self.sender.delete(0, "end")
        self.sender.insert(0, sender)
        self.check()

    def check(self) -> None:
        text = _get(self.message)
        if not text:
            messagebox.showinfo("cedikit", "Paste a payment message first.")
            return
        report = fraud.check(text, sender=self.sender.get().strip() or None)
        style = common.describe(report)
        self.verdict.configure(
            text=f"●  {report.risk} RISK: {style.headline}   (score {report.score:.2f})",
            bg=style.colour,
        )
        lines = [style.advice, ""]
        if report.reasons:
            lines.append("Why:")
            lines += [f"  •  {reason}" for reason in report.reasons]
            lines.append("")
        if not self.sender.get().strip():
            lines.append(
                "Tip: fill in who sent it. Messages from ordinary phone numbers are almost "
                "always fake."
            )
        lines.append(f"Always: {report.advice}")
        _set(self.details, "\n".join(lines), readonly=True)


class LedgerTab(ttk.Frame):
    """Turn MoMo messages into an account book."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, padding=16)
        self.ledger: Ledger | None = None
        self.file_messages: list[dict[str, str]] | None = None

        ttk.Label(self, text="Turn MoMo messages into an account book", style="Title.TLabel").pack(
            anchor="w"
        )
        _hint(
            self,
            "Paste your MoMo messages below (leave an empty line between messages), or open a "
            "file. cedikit reads each one and adds everything up.",
        )
        self.messages = _text_box(self, 4)
        self.messages.pack(fill="x")

        row = ttk.Frame(self)
        row.pack(fill="x", pady=8)
        ttk.Button(row, text="Open file...", command=self.open_file).pack(side="left")
        ttk.Button(row, text="Try with sample messages", command=self.load_sample).pack(
            side="left", padx=6
        )
        ttk.Label(row, text="Sender:").pack(side="left", padx=(12, 4))
        self.sender = ttk.Combobox(row, values=["MobileMoney", "T-CASH", ""], width=14)
        self.sender.set("MobileMoney")
        self.sender.pack(side="left")
        ttk.Button(row, text="Build account book", style="Accent.TButton", command=self.build).pack(
            side="left", padx=12
        )
        self.save_xlsx = ttk.Button(row, text="Save as Excel...", command=lambda: self.save("xlsx"))
        self.save_csv = ttk.Button(row, text="Save as CSV...", command=lambda: self.save("csv"))
        self.save_csv.pack(side="right")
        self.save_xlsx.pack(side="right", padx=6)
        for button in (self.save_xlsx, self.save_csv):
            button.state(["disabled"])

        body = ttk.Frame(self)
        body.pack(fill="x")
        self.summary = ttk.Frame(body, style="Card.TFrame", padding=10)
        self.summary.pack(side="left", fill="y")
        self.notes = ttk.Label(
            body, text="", style="Hint.TLabel", wraplength=px(520), justify="left", padding=(14, 4)
        )
        self.notes.pack(side="left", fill="both", expand=True)

        self.table = _table(
            self,
            common.TRANSACTION_COLUMNS,
            {
                "Date": 125,
                "Network": 65,
                "What": 115,
                "In": 90,
                "Out": 90,
                "Fee": 70,
                "Who": 200,
                "Balance": 95,
                "Category": 140,
            },
        )

    def open_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Open messages",
            filetypes=[("Messages", "*.txt *.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self.file_messages = read_messages(path)
        except (OSError, UnicodeDecodeError, csv.Error) as exc:
            messagebox.showerror("cedikit", f"Could not read the file:\n{exc}")
            return
        preview = "\n\n".join(m["text"] for m in self.file_messages[:20])
        _set(self.messages, preview)
        self.build()

    def load_sample(self) -> None:
        self.file_messages = None
        _set(self.messages, common.SAMPLE_MESSAGES)
        self.sender.set("MobileMoney")
        self.build()

    def build(self) -> None:
        text = _get(self.messages)
        if self.file_messages is not None and text == "\n\n".join(
            m["text"] for m in self.file_messages[:20]
        ):
            source: list[Any] = self.file_messages  # the whole file, not just the preview
        else:
            self.file_messages = None
            source = split_messages(text)
        if not source:
            messagebox.showinfo("cedikit", "Paste some MoMo messages or open a file first.")
            return
        self.ledger = Ledger.from_messages(source, sender=self.sender.get() or None).categorise()

        for child in self.summary.winfo_children():
            child.destroy()
        for r, (label, value) in enumerate(common.summary_items(self.ledger)):
            ttk.Label(self.summary, text=label, style="Card.TLabel").grid(
                row=r, column=0, sticky="w", padx=(0, 16)
            )
            ttk.Label(self.summary, text=value, style="CardValue.TLabel").grid(
                row=r, column=1, sticky="e"
            )
        notes = common.ledger_notes(self.ledger)
        self.notes.configure(text="\n\n".join(notes) if notes else "Everything adds up.")
        _fill(self.table, common.transaction_rows(self.ledger))
        for button in (self.save_xlsx, self.save_csv):
            button.state(["!disabled"])

    def save(self, fmt: str) -> None:
        if self.ledger is None:
            return
        path = filedialog.asksaveasfilename(
            title="Save account book",
            defaultextension=f".{fmt}",
            initialfile=f"momo_ledger.{fmt}",
            filetypes=[("Excel workbook", "*.xlsx")] if fmt == "xlsx" else [("CSV", "*.csv")],
        )
        if not path:
            return
        try:
            self.ledger.export(path, fmt)  # type: ignore[arg-type]
        except (OSError, ImportError) as exc:
            messagebox.showerror("cedikit", f"Could not save:\n{exc}")
            return
        messagebox.showinfo("cedikit", f"Saved:\n{path}")


class PhonesTab(ttk.Frame):
    """Clean up a list of phone numbers."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, padding=16)
        self.csv_rows: list[dict[str, str]] | None = None
        self.csv_fields: list[str] = []
        self.report: phone.CleanReport | None = None

        ttk.Label(self, text="Clean up phone numbers", style="Title.TLabel").pack(anchor="w")
        _hint(
            self,
            "Paste numbers (one per line) or open a CSV file of customers. cedikit writes every "
            "number the same way (+233...), shows the likely network, and flags bad numbers.",
        )
        self.numbers = _text_box(self, 6)
        self.numbers.pack(fill="x")

        row = ttk.Frame(self)
        row.pack(fill="x", pady=8)
        ttk.Button(row, text="Open CSV...", command=self.open_csv).pack(side="left")
        ttk.Label(row, text="Column:").pack(side="left", padx=(8, 4))
        self.column = ttk.Combobox(row, values=[], state="readonly", width=14)
        self.column.pack(side="left")
        ttk.Button(row, text="Try with samples", command=self.load_sample).pack(side="left", padx=6)
        ttk.Button(row, text="Clean numbers", style="Accent.TButton", command=self.clean).pack(
            side="left", padx=6
        )
        self.save_button = ttk.Button(row, text="Save cleaned list...", command=self.save)
        self.save_button.pack(side="right")
        self.save_button.state(["disabled"])

        self.result = ttk.Label(self, text="", style="Strong.TLabel")
        self.result.pack(anchor="w")
        self.table = _table(
            self,
            ["Original", "Cleaned", "Network", "Status", "Note"],
            {"Original": 170, "Cleaned": 150, "Network": 90, "Status": 80, "Note": 380},
        )

    def open_csv(self) -> None:
        path = filedialog.askopenfilename(title="Open CSV", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            with open(path, newline="", encoding="utf-8-sig") as fh:
                reader = csv.DictReader(fh)
                self.csv_rows = list(reader)
                self.csv_fields = list(reader.fieldnames or [])
        except (OSError, UnicodeDecodeError, csv.Error) as exc:
            messagebox.showerror("cedikit", f"Could not read the file:\n{exc}")
            return
        self.column.configure(values=self.csv_fields)
        guess = next((f for f in self.csv_fields if "phone" in f.lower()), self.csv_fields[0])
        self.column.set(guess)
        _set(self.numbers, f"[{len(self.csv_rows)} rows loaded from {Path(path).name}]")
        self.clean()

    def load_sample(self) -> None:
        self.csv_rows = None
        _set(self.numbers, common.SAMPLE_PHONES)
        self.clean()

    def _values(self) -> list[str]:
        if self.csv_rows is not None and _get(self.numbers).startswith("["):
            return [row.get(self.column.get(), "") for row in self.csv_rows]
        self.csv_rows = None
        return [line for line in _get(self.numbers).splitlines() if line.strip()]

    def clean(self) -> None:
        values = self._values()
        if not values:
            messagebox.showinfo("cedikit", "Paste some phone numbers or open a CSV file first.")
            return
        self.report = phone.clean_column(values)
        self.result.configure(text=str(self.report))
        _fill(self.table, common.phone_rows(self.report), bad="Invalid")
        self.save_button.state(["!disabled"])

    def save(self) -> None:
        if self.report is None:
            return
        path = filedialog.asksaveasfilename(
            title="Save cleaned numbers",
            defaultextension=".csv",
            initialfile="cleaned_numbers.csv",
            filetypes=[("CSV", "*.csv")],
        )
        if not path:
            return
        rows = common.phone_rows(self.report)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            if self.csv_rows is not None:
                fields = [*self.csv_fields, "phone_cleaned", "network", "status", "note"]
                writer = csv.DictWriter(fh, fieldnames=fields)
                writer.writeheader()
                for original, row in zip(self.csv_rows, rows, strict=True):
                    writer.writerow(
                        {
                            **original,
                            "phone_cleaned": row["Cleaned"],
                            "network": row["Network"],
                            "status": row["Status"],
                            "note": row["Note"],
                        }
                    )
            else:
                writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
        messagebox.showinfo("cedikit", f"Saved:\n{path}")


class MoneyTab(ttk.Frame):
    """Amounts in words, and fee estimates."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, padding=16)
        ttk.Label(self, text="Money", style="Title.TLabel").pack(anchor="w")
        _hint(self, "Type an amount, e.g. 1200.50, GHS 1,200.50 or 1.2k.")
        row = ttk.Frame(self)
        row.pack(fill="x")
        self.amount = ttk.Entry(row, width=20, font=(FONT, 11))
        self.amount.pack(side="left")
        self.amount.bind("<Return>", lambda _e: self.show_amount())
        ttk.Button(row, text="Show", style="Accent.TButton", command=self.show_amount).pack(
            side="left", padx=8
        )
        self.amount_result = ttk.Label(
            self, text="", style="Strong.TLabel", wraplength=px(880), justify="left"
        )
        self.amount_result.pack(anchor="w", pady=(8, 18))

        ttk.Label(self, text="Estimate MoMo charges", style="Title.TLabel").pack(anchor="w")
        _hint(
            self,
            "Estimates only: based on real messages and published tariffs. Unknown charges are "
            "shown as unknown. Check your network's official tariff.",
        )
        grid = ttk.Frame(self)
        grid.pack(anchor="w")
        ttk.Label(grid, text="Network").grid(row=0, column=0, sticky="w")
        ttk.Label(grid, text="Transaction").grid(row=0, column=1, sticky="w", padx=8)
        ttk.Label(grid, text="Amount (GHS)").grid(row=0, column=2, sticky="w")
        ttk.Label(grid, text="Date (YYYY-MM-DD)").grid(row=0, column=3, sticky="w", padx=8)
        self.network = ttk.Combobox(grid, values=["MTN", "TELECEL"], state="readonly", width=10)
        self.network.set("MTN")
        self.kind = ttk.Combobox(
            grid, values=list(common.FEE_KINDS.values()), state="readonly", width=28
        )
        self.kind.set(common.FEE_KINDS["cash_out"])
        self.fee_amount = ttk.Entry(grid, width=12)
        self.fee_amount.insert(0, "500")
        self.day = ttk.Entry(grid, width=14)
        self.day.insert(0, date.today().isoformat())
        self.network.grid(row=1, column=0)
        self.kind.grid(row=1, column=1, padx=8)
        self.fee_amount.grid(row=1, column=2)
        self.day.grid(row=1, column=3, padx=8)
        ttk.Button(grid, text="Estimate", style="Accent.TButton", command=self.estimate).grid(
            row=1, column=4
        )
        self.fee_result = _text_box(self, 9)
        self.fee_result.configure(background=CARD, relief="flat")
        self.fee_result.pack(fill="both", expand=True, pady=(10, 0))

    def show_amount(self) -> None:
        try:
            value = money.parse(self.amount.get())
        except CedikitError as exc:
            self.amount_result.configure(text=str(exc), foreground=RED)
            return
        self.amount_result.configure(
            text=f"{money.format(value)}    ({money.format(value, 'code')})\n"
            f"{money.to_words(value)}",
            foreground=INK,
        )

    def estimate(self) -> None:
        try:
            day = date.fromisoformat(self.day.get().strip())
            text = common.estimate_fee(
                self.network.get(), self.kind.get(), self.fee_amount.get(), day
            )
        except (ValueError, CedikitError) as exc:
            text = f"Please check the details: {exc}"
        _set(self.fee_result, text, readonly=True)


class IdsTab(ttk.Frame):
    """Ghana Card and digital address checks."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, padding=16)
        ttk.Label(
            self, text="Check a Ghana Card number or digital address", style="Title.TLabel"
        ).pack(anchor="w")
        _hint(
            self,
            "Checks that it is written correctly, e.g. GHA-123456789-0 or AK-039-5028. It does "
            "not check that the card or address really exists.",
        )
        row = ttk.Frame(self)
        row.pack(fill="x")
        self.value = ttk.Entry(row, width=28, font=(FONT, 11))
        self.value.pack(side="left")
        self.value.bind("<Return>", lambda _e: self.check())
        ttk.Button(row, text="Check", style="Accent.TButton", command=self.check).pack(
            side="left", padx=8
        )
        self.result = tk.Label(
            self, text="", font=(FONT, 12), anchor="w", justify="left", padx=12, pady=10,
            wraplength=px(860), bg=PAPER,
        )  # fmt: skip
        self.result.pack(fill="x", pady=12)

    def check(self) -> None:
        outcome = common.check_id(self.value.get())
        self.result.configure(
            text=("✔  " if outcome.ok else "✖  ") + outcome.message,
            fg="white",
            bg=GREEN if outcome.ok else RED,
        )


class AboutTab(ttk.Frame):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, padding=24)
        ttk.Label(self, text=f"cedikit {__version__}", style="Title.TLabel").pack(anchor="w")
        text = (
            "cedikit helps Ghanaian businesses with Mobile Money:\n\n"
            "   •  Check whether a payment message is real or fake\n"
            "   •  Turn MoMo messages into an account book and save it to Excel\n"
            "   •  Clean up lists of customers' phone numbers\n"
            "   •  Write amounts in words and estimate MoMo charges\n"
            "   •  Check Ghana Card numbers and GhanaPostGPS addresses\n\n"
            "Everything runs on this computer. Nothing you type is sent online.\n\n"
            "⚠  cedikit is a helper, not a bank. Before handing over goods, always confirm the "
            "payment in your official Mobile Money app or with your network's official USSD code."
        )
        ttk.Label(self, text=text, wraplength=px(820), justify="left", font=(FONT, 11)).pack(
            anchor="w", pady=(8, 16)
        )
        links = ttk.Frame(self)
        links.pack(anchor="w")
        ttk.Button(links, text="Documentation", command=lambda: webbrowser.open(DOCS)).pack(
            side="left"
        )
        ttk.Button(links, text="Source code", command=lambda: webbrowser.open(REPO)).pack(
            side="left", padx=8
        )
        ttk.Label(
            self,
            text="Made by Francis Kusi, KNUST School of Business. Free and open source (MIT).",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(20, 0))


# -- the window ---------------------------------------------------------------------------


def _style(root: tk.Tk | tk.Toplevel) -> None:
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    root.configure(background=PAPER)
    style.configure(".", font=(FONT, 10), background=PAPER, foreground=INK)
    style.configure("TFrame", background=PAPER)
    style.configure("TLabel", background=PAPER)
    style.configure("Title.TLabel", font=(FONT, 14, "bold"), foreground=GREEN)
    style.configure("Hint.TLabel", foreground=MUTED)
    style.configure("Strong.TLabel", font=(FONT, 11, "bold"))
    style.configure("Card.TFrame", background=CARD, relief="solid", borderwidth=1)
    style.configure("Card.TLabel", background=CARD, foreground=MUTED)
    style.configure("CardValue.TLabel", background=CARD, font=(FONT, 10, "bold"))
    style.configure("TNotebook", background=PAPER, borderwidth=0)
    style.configure("TNotebook.Tab", padding=(14, 7), font=(FONT, 10, "bold"))
    style.map("TNotebook.Tab", background=[("selected", CARD)], foreground=[("selected", GREEN)])
    style.configure("Accent.TButton", background=GREEN, foreground="white", padding=(12, 5))
    style.map("Accent.TButton", background=[("active", "#00552f"), ("disabled", "#9ca3af")])
    style.configure("Treeview", rowheight=px(24), font=(FONT, 9))
    style.configure("Treeview.Heading", font=(FONT, 9, "bold"))


class CedikitApp:
    """The app, built in ``root``: the main window, or a child window.

    ``tabs`` gives access to each tab (used by the tests).
    """

    def __init__(self, root: tk.Tk | tk.Toplevel) -> None:
        self.root = root
        root.title("cedikit: Mobile Money helper")
        icon = Path(__file__).with_name("cedikit.ico")
        if sys.platform == "win32" and icon.exists():
            with contextlib.suppress(tk.TclError):  # a damaged icon shouldn't stop the app
                root.iconbitmap(default=str(icon))  # type: ignore[no-untyped-call]
        global _SCALE
        _SCALE = max(root.winfo_fpixels("1i") / 96, 1.0)
        # Fit the screen (leaving room for the taskbar), centred.
        width = min(px(1040), int(root.winfo_screenwidth() * 0.92))
        height = min(px(720), int(root.winfo_screenheight() * 0.85))
        x = (root.winfo_screenwidth() - width) // 2
        y = max((root.winfo_screenheight() - height) // 2 - px(20), 0)
        root.geometry(f"{width}x{height}+{x}+{y}")
        root.minsize(min(px(860), width), min(px(560), height))
        _style(root)

        header = tk.Frame(root, background=INK)
        header.pack(fill="x")
        stripe = tk.Frame(header, height=px(5))
        stripe.pack(fill="x")
        for colour in (RED, GOLD, GREEN):
            tk.Frame(stripe, background=colour, height=px(5)).pack(
                side="left", fill="x", expand=True
            )
        title = tk.Frame(header, background=INK, padx=16, pady=10)
        title.pack(fill="x")
        tk.Label(
            title, text="₵", font=(FONT, 22, "bold"), fg=GOLD, bg=INK
        ).pack(side="left")  # fmt: skip
        tk.Label(title, text=" cedikit", font=(FONT, 18, "bold"), fg="white", bg=INK).pack(
            side="left"
        )
        tk.Label(
            title,
            text="   Mobile Money helper for Ghanaian businesses",
            font=(FONT, 10),
            fg="#d1d5db",
            bg=INK,
        ).pack(side="left", pady=(6, 0))

        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True, padx=10, pady=(8, 0))
        self.notebook = notebook
        self.tabs: dict[str, ttk.Frame] = {
            "check": CheckTab(notebook),
            "ledger": LedgerTab(notebook),
            "phones": PhonesTab(notebook),
            "money": MoneyTab(notebook),
            "ids": IdsTab(notebook),
            "about": AboutTab(notebook),
        }
        labels = {
            "check": "  ⚠  Check a message  ",
            "ledger": "  Account book  ",
            "phones": "  Phone numbers  ",
            "money": "  Money & fees  ",
            "ids": "  Ghana Card & address  ",
            "about": "  About  ",
        }
        for key, tab in self.tabs.items():
            notebook.add(tab, text=labels[key])

        tk.Label(
            root,
            text="Everything runs on this computer. Nothing is sent online.",
            font=(FONT, 9),
            fg=MUTED,
            bg=PAPER,
            anchor="w",
            padx=12,
            pady=4,
        ).pack(fill="x")


def _selftest(app: CedikitApp, screenshots: Path | None) -> None:
    """Exercise every tab (used by tests and to check packaged builds)."""
    check = app.tabs["check"]
    assert isinstance(check, CheckTab)
    check.example.set("Fake cash-in")
    check._load_example()
    ledger = app.tabs["ledger"]
    assert isinstance(ledger, LedgerTab)
    ledger.load_sample()
    assert ledger.ledger is not None and len(ledger.ledger) == 6
    with tempfile.TemporaryDirectory() as tmp:  # proves Excel support is bundled
        for fmt in ("xlsx", "csv"):
            assert ledger.ledger.export(Path(tmp) / f"selftest.{fmt}").stat().st_size > 0
    phones = app.tabs["phones"]
    assert isinstance(phones, PhonesTab)
    phones.load_sample()
    money_tab = app.tabs["money"]
    assert isinstance(money_tab, MoneyTab)
    money_tab.amount.insert(0, "1250.50")
    money_tab.show_amount()
    money_tab.estimate()
    ids = app.tabs["ids"]
    assert isinstance(ids, IdsTab)
    ids.value.insert(0, "AK-039-5028")
    ids.check()
    app.root.update()
    if screenshots is not None:
        from PIL import ImageGrab

        screenshots.mkdir(parents=True, exist_ok=True)
        for key, tab in app.tabs.items():
            app.notebook.select(tab)  # type: ignore[no-untyped-call]
            app.root.update()
            time.sleep(0.4)  # let the tab finish drawing
            app.root.update()
            r = app.root
            left, top = r.winfo_rootx(), r.winfo_rooty()
            box = (left, top, left + r.winfo_width(), top + r.winfo_height())
            ImageGrab.grab(bbox=box, all_screens=True).save(screenshots / f"desktop_{key}.png")
    print("cedikit desktop self-test passed")


def _enable_sharp_text() -> None:
    """Tell Windows the app handles screen scaling itself, so text isn't blurry."""
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):  # pragma: no cover - older Windows
            pass


def main(argv: list[str] | None = None) -> None:
    """Open the desktop app."""
    parser = argparse.ArgumentParser(prog="cedikit-app", description="cedikit desktop app")
    parser.add_argument("--selftest", action="store_true", help="run every tab, then exit")
    parser.add_argument("--screenshots", type=Path, help="with --selftest: save tab images here")
    args = parser.parse_args(argv)

    _enable_sharp_text()
    root = tk.Tk()
    app = CedikitApp(root)
    if args.selftest:
        passed = False

        def run_selftest() -> None:
            nonlocal passed
            try:
                _selftest(app, args.screenshots)
                passed = True
            finally:
                root.quit()  # ends mainloop, even when root is a child window
                root.destroy()

        root.after(300, run_selftest)
        root.mainloop()
        if not passed:
            raise SystemExit("cedikit desktop self-test FAILED")
        return
    root.mainloop()


if __name__ == "__main__":  # pragma: no cover
    main()
