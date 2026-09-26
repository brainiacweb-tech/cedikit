"""Tests for the desktop and web apps and their shared helpers."""

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from cedikit import fraud, phone
from cedikit.app import common
from cedikit.fees import Kind
from cedikit.ledger import Ledger, read_messages, split_messages

WEB_APP = Path(__file__).parents[1] / "src" / "cedikit" / "app" / "web.py"
_KEEP_TK_ALIVE: list[Any] = []


# -- shared helpers -----------------------------------------------------------------------


def _sample_ledger() -> Ledger:
    messages = split_messages(common.SAMPLE_MESSAGES)
    return Ledger.from_messages(messages, sender="MobileMoney").categorise()


def test_fee_kinds_cover_every_fee_kind() -> None:
    assert set(common.FEE_KINDS) == set(Kind.__args__)  # type: ignore[attr-defined]


def test_samples_make_a_clean_ledger() -> None:
    ledger = _sample_ledger()
    assert len(ledger) == 6 and not ledger.unrecognised and ledger.balance_gaps() == []
    rows = common.transaction_rows(ledger)
    assert rows[0]["What"] == "Money received" and rows[0]["In"] == "GH₵ 120.00"
    assert rows[3]["Out"] == "GH₵ 100.00" and rows[3]["Fee"] == "GH₵ 1.00"
    assert rows[4]["Category"] == "loan repayment"
    labels = dict(common.summary_items(ledger))
    assert labels["Money in"] == "GH₵ 245.00" and labels["Last MTN balance"] == "GH₵ 94.00"


def test_ledger_notes(genuine: dict[str, dict[str, Any]]) -> None:
    texts = [
        genuine["telecel_cash_in"]["text"],
        genuine["telecel_airtime_received_notice"]["text"],
        genuine["telecel_received_same_network"]["text"],
        genuine["telecel_received_same_network"]["text"],
        "hello",
    ]
    notes = common.ledger_notes(Ledger.from_messages(texts, sender="T-CASH"))
    text = " ".join(notes)
    assert "not recognised" in text and "notice" in text and "duplicate" in text
    assert "Balance jump" in text
    assert common.ledger_notes(_sample_ledger()) == [
        "6 transaction(s) have no date (MTN messages don't include one)."
    ]


def test_phone_rows_and_network_names() -> None:
    report = phone.clean_column(common.SAMPLE_PHONES.splitlines())
    rows = common.phone_rows(report)
    assert [r["Network"] for r in rows[:3]] == ["MTN", "Telecel", "AT"]
    assert rows[5]["Status"] == "Invalid" and "digits" in rows[5]["Note"]
    assert common.network_name(None) == "" and common.network_name("XYZ") == "Xyz"


def test_every_example_gets_the_expected_verdict() -> None:
    risks = {name: fraud.check(text, sender=sender).risk for name, (text, sender) in
             common.EXAMPLES.items()}  # fmt: skip
    assert risks == {"Genuine MTN payment": "LOW", "Fake cash-in": "HIGH",
                     "Fake 'account blocked'": "HIGH"}  # fmt: skip
    report = fraud.check(*common.EXAMPLES["Fake cash-in"])
    assert common.describe(report).headline == "Very likely fake"


def test_estimate_fee_and_check_id() -> None:
    text = common.estimate_fee("MTN", "Cash out (withdraw)", "500", date(2026, 9, 1))
    assert "GH₵ 5.00" in text
    with pytest.raises(ValueError):
        common.estimate_fee("MTN", "Cash out (withdraw)", "lots", None)
    card = common.check_id(" fgn9876543215 ")
    assert card.ok and "foreign national" in card.message and "FGN-98*****21-5" in card.message
    address = common.check_id("ak0395028")
    assert address.ok and "Kumasi Metropolitan, Ashanti" in address.message
    assert not common.check_id("hello").ok


def test_read_messages(tmp_path: Path) -> None:
    txt = tmp_path / "inbox.txt"
    txt.write_text("one\r\n\r\ntwo\nlines\n\n\n", encoding="utf-8")
    assert read_messages(txt) == [{"text": "one"}, {"text": "two\nlines"}]


# -- desktop app ------------------------------------------------------------------------


@pytest.fixture(scope="session")
def tk_root() -> Any:
    """One Tk interpreter for the whole session. Creating and destroying many Tk
    interpreters in one process is fragile (Tcl sometimes fails to find its library),
    so each test opens the app in a child window of this root instead."""
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk unavailable: {exc}")
    root.withdraw()
    # Never let the garbage collector free Tk from another thread (e.g. Streamlit's).
    _KEEP_TK_ALIVE.append(root)
    return root


@pytest.fixture
def desktop(tk_root: Any) -> Any:
    import tkinter as tk

    from cedikit.app import desktop as module

    window = tk.Toplevel(tk_root)
    window.withdraw()
    app = module.CedikitApp(window)
    yield module, app
    window.destroy()
    _KEEP_TK_ALIVE.append((window, app))


def test_desktop_selftest_exercises_every_tab(desktop: Any, tmp_path: Path) -> None:
    module, app = desktop
    module._selftest(app, None)
    check = app.tabs["check"]
    assert "HIGH RISK" in check.verdict.cget("text")
    ledger = app.tabs["ledger"]
    assert len(ledger.table.get_children()) == 6
    assert "no date" in ledger.notes.cget("text")
    phones = app.tabs["phones"]
    assert phones.result.cget("text") == "7 numbers: 0 valid, 5 fixed, 2 invalid"
    money_tab = app.tabs["money"]
    assert "One thousand two hundred and fifty Ghana cedis" in money_tab.amount_result.cget("text")
    assert "GH₵" in money_tab.fee_result.get("1.0", "end")
    ids = app.tabs["ids"]
    assert ids.result.cget("text").startswith("✔")


def test_desktop_edge_cases(desktop: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module, app = desktop
    shown: list[str] = []
    monkeypatch.setattr(module.messagebox, "showinfo", lambda _t, msg: shown.append(msg))
    monkeypatch.setattr(module.messagebox, "showerror", lambda _t, msg: shown.append(msg))

    app.tabs["check"].check()  # empty message
    app.tabs["ledger"].build()  # nothing pasted
    app.tabs["phones"].clean()  # nothing pasted
    assert len(shown) == 3

    check = app.tabs["check"]
    module._set(check.message, common.EXAMPLES["Genuine MTN payment"][0])
    check.check()  # no sender given
    assert "Tip: fill in who sent it" in check.details.get("1.0", "end")

    money_tab = app.tabs["money"]
    money_tab.amount.insert(0, "abc")
    money_tab.show_amount()
    assert "Cannot parse" in money_tab.amount_result.cget("text")
    money_tab.day.delete(0, "end")
    money_tab.day.insert(0, "not a date")
    money_tab.estimate()
    assert "Please check the details" in money_tab.fee_result.get("1.0", "end")

    ids = app.tabs["ids"]
    ids.value.insert(0, "nonsense")
    ids.check()
    assert ids.result.cget("text").startswith("✖")


def test_desktop_files(desktop: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import csv

    module, app = desktop
    monkeypatch.setattr(module.messagebox, "showinfo", lambda *_a: None)

    # Account book: open a file, then save Excel and CSV
    inbox = tmp_path / "inbox.txt"
    inbox.write_text(common.SAMPLE_MESSAGES, encoding="utf-8")
    monkeypatch.setattr(module.filedialog, "askopenfilename", lambda **_k: str(inbox))
    ledger = app.tabs["ledger"]
    ledger.open_file()
    assert len(ledger.table.get_children()) == 6
    for fmt in ("xlsx", "csv"):
        target = tmp_path / f"out.{fmt}"
        monkeypatch.setattr(
            module.filedialog, "asksaveasfilename", lambda target=target, **_k: str(target)
        )
        ledger.save(fmt)
        assert target.stat().st_size > 0

    # Phones: open a CSV, save the cleaned copy with the original columns kept
    customers = tmp_path / "customers.csv"
    customers.write_text("name,phone\nAma,024 412 3456\nKofi,12345\n", encoding="utf-8")
    monkeypatch.setattr(module.filedialog, "askopenfilename", lambda **_k: str(customers))
    phones = app.tabs["phones"]
    phones.open_csv()
    assert phones.column.get() == "phone"
    out = tmp_path / "cleaned.csv"
    monkeypatch.setattr(module.filedialog, "asksaveasfilename", lambda **_k: str(out))
    phones.save()
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert rows[0]["name"] == "Ama" and rows[0]["phone_cleaned"] == "+233244123456"
    assert rows[1]["status"] == "Invalid"

    # Pasted numbers save as a plain table
    phones.load_sample()
    phones.save()
    assert "Cleaned" in out.read_text(encoding="utf-8").splitlines()[0]

    # Cancelled dialogs do nothing
    monkeypatch.setattr(module.filedialog, "askopenfilename", lambda **_k: "")
    monkeypatch.setattr(module.filedialog, "asksaveasfilename", lambda **_k: "")
    ledger.open_file()
    ledger.save("csv")
    phones.open_csv()
    phones.save()


def test_desktop_main_selftest_with_screenshots(
    tk_root: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import tkinter as tk

    from cedikit.app import desktop as module

    windows: list[Any] = []

    def child_window() -> Any:
        windows.append(tk.Toplevel(tk_root))
        return windows[-1]

    monkeypatch.setattr(module.tk, "Tk", child_window)
    module.main(["--selftest", "--screenshots", str(tmp_path)])
    _KEEP_TK_ALIVE.extend(windows)
    assert sorted(p.name for p in tmp_path.glob("*.png")) == [
        f"desktop_{k}.png" for k in sorted(["about", "check", "ids", "ledger", "money", "phones"])
    ]


def test_desktop_unreadable_files(
    desktop: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module, app = desktop
    errors: list[str] = []
    monkeypatch.setattr(module.messagebox, "showerror", lambda _t, msg: errors.append(msg))
    missing = str(tmp_path / "missing.csv")
    monkeypatch.setattr(module.filedialog, "askopenfilename", lambda **_k: missing)
    app.tabs["ledger"].open_file()
    app.tabs["phones"].open_csv()
    assert len(errors) == 2 and all("Could not read" in e for e in errors)


# -- web app ---------------------------------------------------------------------------


@pytest.fixture
def web() -> Any:
    testing = pytest.importorskip("streamlit.testing.v1")
    at = testing.AppTest.from_file(str(WEB_APP), default_timeout=60)
    at.run()
    assert not at.exception
    return at


def _texts(at: Any) -> str:
    parts = [m.value for m in at.markdown] + [e.value for e in at.info]
    parts += [e.value for e in at.success] + [e.value for e in at.error]
    parts += [e.value for e in at.warning] + [c.value for c in at.code]
    return "\n".join(str(p) for p in parts)


def test_web_check_tab(web: Any) -> None:
    web.selectbox(key="example").select("Fake cash-in").run()
    web.button(key="check_button").click().run()
    assert not web.exception
    assert "HIGH RISK: Very likely fake" in _texts(web)

    web.text_input(key="check_sender").input("").run()
    web.button(key="check_button").click().run()
    assert "Tip: fill in who sent it" in _texts(web)


def test_web_ledger_and_phones(web: Any) -> None:
    web.button(key="ledger_sample").click().run()
    web.button(key="phones_sample").click().run()
    assert not web.exception
    metrics = {m.label: m.value for m in web.metric}
    assert metrics["Money in"] == "GH₵ 245.00" and metrics["Net"] == "-GH₵ 106.00"
    assert "7 numbers: 0 valid, 5 fixed, 2 invalid" in _texts(web)
    assert len(web.dataframe) == 2


def test_web_money_fees_and_ids(web: Any) -> None:
    web.text_input(key="money_amount").input("1250.50").run()
    web.text_input(key="id_value").input("ak0395028").run()
    assert not web.exception
    text = _texts(web)
    assert "One thousand two hundred and fifty Ghana cedis and fifty pesewas" in text
    assert "Kumasi Metropolitan" in text
    assert "Estimated charges" in text

    web.text_input(key="money_amount").input("abc").run()
    web.text_input(key="id_value").input("nonsense").run()
    web.text_input(key="fee_amount").input("lots").run()
    text = _texts(web)
    assert "Cannot parse" in text and "not a correctly written" in text
    assert "Please check the details" in text


def test_cli_launchers(monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    from cedikit import cli

    calls: list[Any] = []
    monkeypatch.setattr("cedikit.app.desktop.main", lambda argv: calls.append(("app", argv)))
    monkeypatch.setattr("subprocess.call", lambda cmd: calls.append(("web", cmd)) or 0)
    runner = CliRunner()
    assert runner.invoke(cli.app, ["app"]).exit_code == 0
    result = runner.invoke(cli.app, ["web", "--port", "8600"])
    assert result.exit_code == 0 and "localhost:8600" in result.output
    web_cmd = calls[1][1]
    assert "--browser.gatherUsageStats" in web_cmd and "localhost" in web_cmd
    assert calls[0] == ("app", [])

    monkeypatch.setattr("importlib.util.find_spec", lambda _name: None)
    missing = runner.invoke(cli.app, ["web"])
    assert missing.exit_code == 1 and "cedikit[web]" in missing.output


def test_python_dash_m(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import runpy
    import sys

    monkeypatch.setattr(sys, "argv", ["cedikit", "--version"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("cedikit", run_name="__main__")
    assert exc.value.code == 0
    assert "cedikit" in capsys.readouterr().out
