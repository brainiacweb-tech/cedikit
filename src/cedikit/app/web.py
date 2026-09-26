"""The cedikit web app (Streamlit).

Start it with ``cedikit web`` (needs ``pip install "cedikit[web]"``). It runs on your
own computer at http://localhost:8501; the launcher turns off Streamlit's usage
statistics, so nothing is sent online.
"""

from __future__ import annotations

import csv
import io
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

import streamlit as st

from cedikit import __version__, fraud, money, phone
from cedikit.app import common
from cedikit.exceptions import CedikitError
from cedikit.ledger import Ledger, read_messages, split_messages

GREEN, GOLD, RED = "#006B3F", "#FCD116", "#CE1126"


def _header() -> None:
    st.markdown(
        f"""
        <div style="height:6px;background:linear-gradient(90deg,{RED} 0 33.3%,{GOLD} 33.3% 66.6%,
             {GREEN} 66.6% 100%);border-radius:3px;margin-bottom:10px"></div>
        <div style="display:flex;align-items:center;gap:12px">
          <div style="font-size:2.4rem;font-weight:800;color:{GOLD};background:#111;
               border-radius:50%;width:3.2rem;height:3.2rem;display:flex;align-items:center;
               justify-content:center">₵</div>
          <div>
            <div style="font-size:2rem;font-weight:800;line-height:1">
              <span style="color:{GREEN}">cedi</span><span style="color:{RED}">kit</span></div>
            <div style="color:#6b7280">Mobile Money helper for Ghanaian businesses</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _banner(colour: str, text: str) -> None:
    st.markdown(
        f'<div style="background:{colour};color:white;padding:14px 18px;border-radius:10px;'
        f'font-size:1.35rem;font-weight:700;margin:8px 0">{text}</div>',
        unsafe_allow_html=True,
    )


def _upload_to_path(upload: Any) -> Path:
    """Save an uploaded file to a temporary path (cedikit's readers take paths)."""
    suffix = Path(upload.name).suffix or ".txt"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as fh:
        fh.write(upload.getvalue())
    return Path(fh.name)


def _set_example() -> None:
    choice = st.session_state.get("example")
    if choice in common.EXAMPLES:
        text, sender = common.EXAMPLES[choice]
        st.session_state["check_text"] = text
        st.session_state["check_sender"] = sender


# -- tabs -------------------------------------------------------------------------------


def check_tab() -> None:
    st.subheader("Is this payment message real?")
    st.caption(
        "Paste the MoMo message you received and who it came from. cedikit looks for the "
        "warning signs of a fake alert and explains what it finds."
    )
    st.selectbox(
        "Or try an example",
        ["", *common.EXAMPLES],
        key="example",
        on_change=_set_example,
        format_func=lambda x: x or "Choose an example...",
    )
    text = st.text_area("Payment message", key="check_text", height=150)
    sender = st.text_input("Sent by (the name or number shown on your phone)", key="check_sender")
    if st.button("Check message", type="primary", key="check_button"):
        if not text.strip():
            st.info("Paste a payment message first.")
            return
        report = fraud.check(text, sender=sender.strip() or None)
        style = common.describe(report)
        _banner(
            style.colour,
            f"{style.icon} {report.risk} RISK: {style.headline} (score {report.score:.2f})",
        )
        st.markdown(f"**{style.advice}**")
        if report.reasons:
            st.markdown("**Why:**")
            for reason in report.reasons:
                st.markdown(f"- {reason}")
        if not sender.strip():
            st.info(
                "Tip: fill in who sent it. Messages from ordinary phone numbers are almost "
                "always fake."
            )
        st.warning(report.advice, icon="⚠️")


def ledger_tab() -> None:
    st.subheader("Turn MoMo messages into an account book")
    st.caption(
        "Paste your MoMo messages (an empty line between messages) or upload a file. "
        "cedikit reads each one and adds everything up."
    )
    left, right = st.columns([3, 1])
    with right:
        upload = st.file_uploader("Upload a file", type=["txt", "csv"], key="ledger_file")
        if st.button("Try with sample messages", key="ledger_sample"):
            st.session_state["ledger_text"] = common.SAMPLE_MESSAGES
            st.session_state["ledger_sender"] = "MobileMoney"
        sender = st.selectbox(
            "Sender", ["MobileMoney", "T-CASH", ""], key="ledger_sender",
            format_func=lambda x: x or "(not known)",
        )  # fmt: skip
    with left:
        text = st.text_area("MoMo messages", key="ledger_text", height=210)

    source: list[Any] = (
        read_messages(_upload_to_path(upload)) if upload is not None else split_messages(text)
    )
    if not source:
        st.info("Paste some messages, upload a file, or try the samples.")
        return

    ledger = Ledger.from_messages(source, sender=sender or None).categorise()
    s = ledger.summary()
    cols = st.columns(4)
    cols[0].metric("Money in", money.format(s.total_in))
    cols[1].metric("Money out", money.format(s.total_out))
    cols[2].metric("Fees paid", money.format(s.fees))
    cols[3].metric("Net", money.format(s.net))
    with st.expander("Full summary", expanded=False):
        for label, value in common.summary_items(ledger):
            st.markdown(f"**{label}:** {value}")
    for note in common.ledger_notes(ledger):
        st.info(note)

    st.dataframe(common.transaction_rows(ledger), width="stretch", hide_index=True)
    totals = ledger.category_totals()
    if totals:
        st.markdown("**Amount per category (GHS)**")
        st.bar_chart({"GHS": {k: float(v) for k, v in totals.items()}})

    with tempfile.TemporaryDirectory() as tmp:
        csv_path = ledger.export(Path(tmp) / "ledger.csv")
        csv_bytes = csv_path.read_bytes()
        try:
            xlsx_bytes = ledger.export(Path(tmp) / "ledger.xlsx").read_bytes()
        except ImportError:
            xlsx_bytes = None
    d1, d2 = st.columns(2)
    if xlsx_bytes is not None:
        d1.download_button(
            "Download Excel", xlsx_bytes, "momo_ledger.xlsx", key="dl_xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )  # fmt: skip
    d2.download_button("Download CSV", csv_bytes, "momo_ledger.csv", "text/csv", key="dl_csv")


def phones_tab() -> None:
    st.subheader("Clean up phone numbers")
    st.caption(
        "Paste numbers (one per line) or upload a CSV of customers. cedikit writes every "
        "number the same way (+233...), shows the likely network and flags bad numbers."
    )
    if st.button("Try with samples", key="phones_sample"):
        st.session_state["phones_text"] = common.SAMPLE_PHONES
    upload = st.file_uploader("Upload a CSV", type=["csv"], key="phones_file")
    rows: list[dict[str, str]] | None = None
    if upload is not None:
        reader = csv.DictReader(io.StringIO(upload.getvalue().decode("utf-8-sig")))
        rows = list(reader)
        fields = list(reader.fieldnames or [])
        guess = next((i for i, f in enumerate(fields) if "phone" in f.lower()), 0)
        column = st.selectbox("Which column has the phone numbers?", fields, index=guess)
        values = [row.get(column, "") for row in rows]
    else:
        text = st.text_area("Phone numbers", key="phones_text", height=170)
        values = [line for line in text.splitlines() if line.strip()]
    if not values:
        return

    report = phone.clean_column(values)
    st.markdown(f"**{report}**")
    table = common.phone_rows(report)
    st.dataframe(table, width="stretch", hide_index=True)

    out = io.StringIO()
    if rows is not None:
        writer = csv.DictWriter(
            out, fieldnames=[*rows[0], "phone_cleaned", "network", "status", "note"]
        )
        writer.writeheader()
        for original, row in zip(rows, table, strict=True):
            writer.writerow({**original, "phone_cleaned": row["Cleaned"],
                             "network": row["Network"], "status": row["Status"],
                             "note": row["Note"]})  # fmt: skip
    else:
        writer = csv.DictWriter(out, fieldnames=list(table[0]))
        writer.writeheader()
        writer.writerows(table)
    st.download_button(
        "Download cleaned list", out.getvalue().encode("utf-8"), "cleaned_numbers.csv",
        "text/csv", key="dl_phones",
    )  # fmt: skip


def money_tab() -> None:
    st.subheader("Money")
    amount = st.text_input("Amount (e.g. 1200.50, GHS 1,200.50 or 1.2k)", key="money_amount")
    if amount.strip():
        try:
            value = money.parse(amount)
        except CedikitError as exc:
            st.error(str(exc))
        else:
            st.success(f"{money.format(value)}  ({money.format(value, 'code')})")
            st.markdown(f"**In words:** {money.to_words(value)}")

    st.subheader("Estimate MoMo charges")
    st.caption(
        "Estimates only: based on real messages and published tariffs. Unknown charges are "
        "shown as unknown. Check your network's official tariff."
    )
    c1, c2, c3, c4 = st.columns([1, 2, 1, 1])
    network = c1.selectbox("Network", ["MTN", "TELECEL"], key="fee_network")
    kind = c2.selectbox("Transaction", list(common.FEE_KINDS.values()), index=2, key="fee_kind")
    fee_amount = c3.text_input("Amount (GHS)", "500", key="fee_amount")
    day = c4.date_input("Date", date.today(), key="fee_date")
    try:
        st.code(common.estimate_fee(network, kind, fee_amount, day), language=None)
    except (ValueError, CedikitError) as exc:
        st.error(f"Please check the details: {exc}")


def ids_tab() -> None:
    st.subheader("Check a Ghana Card number or digital address")
    st.caption(
        "Checks that it is written correctly, e.g. GHA-123456789-0 or AK-039-5028. It does not "
        "check that the card or address really exists."
    )
    value = st.text_input("Ghana Card number or GhanaPostGPS address", key="id_value")
    if value.strip():
        outcome = common.check_id(value)
        (st.success if outcome.ok else st.error)(outcome.message)


def about_tab() -> None:
    st.subheader(f"cedikit {__version__}")
    st.markdown(
        """
cedikit helps Ghanaian businesses with Mobile Money:

- Check whether a payment message is **real or fake**
- Turn MoMo messages into an **account book** and download it for Excel
- **Clean up** lists of customers' phone numbers
- Write amounts **in words** and **estimate MoMo charges**
- Check **Ghana Card** numbers and **GhanaPostGPS** addresses

Everything runs on this computer. Nothing you type is sent online.

[Documentation](https://cedikit.readthedocs.io/) ·
[Source code](https://github.com/brainiacweb-tech/cedikit) ·
Made by Francis Kusi, KNUST School of Business. Free and open source (MIT).
"""
    )
    st.warning(
        "cedikit is a helper, not a bank. Before handing over goods, always confirm the payment "
        "in your official Mobile Money app or with your network's official USSD code.",
        icon="⚠️",
    )


def main() -> None:
    st.set_page_config(page_title="cedikit", page_icon="₵", layout="wide")
    _header()
    tabs = st.tabs(
        [
            "🚨 Check a message",
            "📒 Account book",
            "📱 Phone numbers",
            "💰 Money & fees",
            "🪪 Ghana Card & address",
            "📘 About",
        ]
    )
    for tab, render in zip(
        tabs, [check_tab, ledger_tab, phones_tab, money_tab, ids_tab, about_tab], strict=True
    ):
        with tab:
            render()
    st.caption("Everything runs on this computer. Nothing is sent online.")


main()
