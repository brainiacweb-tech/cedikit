"""Build and execute notebooks/demo.ipynb (run from the repository root).

python notebooks/build_demo.py
"""

from pathlib import Path
from textwrap import dedent

import nbformat
from nbclient import NotebookClient

HERE = Path(__file__).parent


def md(text: str) -> nbformat.NotebookNode:
    return nbformat.v4.new_markdown_cell(dedent(text).strip())


def code(text: str) -> nbformat.NotebookNode:
    return nbformat.v4.new_code_cell(dedent(text).strip())


cells = [
    md("""
        # cedikit demo

        From messy phone numbers and raw MoMo SMS to a clean ledger, charts and fraud warnings.
        All data here is synthetic or anonymised (see `examples/make_demo_data.py`).
    """),
    code("""
        %matplotlib inline
        import csv
        from datetime import date

        import pandas as pd

        import cedikit
        import cedikit.integrations.pandas_accessor  # registers df[col].cedikit
        from cedikit import Cedi, fees, fraud, money, phone
        from cedikit.ledger import Ledger

        cedikit.__version__
    """),
    md("""
        ## 1. Messy phone numbers

        500 customer numbers typed every way people type them.
    """),
    code("""
        customers = pd.read_csv("../examples/customers.csv", dtype=str)
        customers.head(8)
    """),
    code("""
        customers["e164"] = customers["phone"].cedikit.normalise()
        customers["network"] = customers["phone"].cedikit.likely_network()
        print(phone.clean_column(customers["phone"]))
        customers.head(8)
    """),
    code('customers["network"].value_counts(dropna=False)'),
    md("## 2. Money: why floats are dangerous"),
    code("0.1 + 0.2"),
    code("""
        print(sum([Cedi("0.10"), Cedi("0.20")]))
        print(money.parse("GH₵1.2k"))
        print(money.to_words("1200.50"))
    """),
    code("""
        try:
            money.format(1200.5)
        except cedikit.CediTypeError as exc:
            print(exc)
    """),
    md("## 3. A month of MoMo SMS → ledger"),
    code("""
        with open("../examples/inbox.csv", encoding="utf-8") as fh:
            messages = list(csv.DictReader(fh))
        print(len(messages), "messages")
        print(messages[0]["text"])
    """),
    code("""
        ledger = Ledger.from_messages(messages).categorise()
        print(ledger.summary())
        print(len(ledger.notices), "notices;", len(ledger.balance_gaps()), "balance gaps")
    """),
    code('pd.Series({k: float(v) for k, v in ledger.category_totals().items()}, name="GHS")'),
    code("""
        pd.DataFrame(
            [(p.start, p.inflow, p.outflow, p.net) for p in ledger.cash_flow("week")],
            columns=["week", "in", "out", "net"],
        )
    """),
    code('[(c.name, c.count, c.total) for c in ledger.top_counterparties(3, by="value")]'),
    code('ledger.plot("cash_flow", period="week")'),
    code('ledger.plot("categories")'),
    code('ledger.export("september_ledger.xlsx")'),
    md("## 4. Fake payment alerts"),
    code("""
        genuine = messages[0]
        print(fraud.check(genuine["text"], sender=genuine["sender"]))
    """),
    code("""
        with open("../examples/suspicious.txt", encoding="utf-8") as fh:
            fake = fh.read().split("\\n\\n")[0]
        print(fake, end="\\n\\n")
        print(fraud.check(fake, sender="+233591234567", history=ledger.transactions))
    """),
    code("""
        copy = messages[0]["text"]  # a perfect copy of a real alert...
        print(fraud.check(copy, sender="0551234567"))  # ...sent from a personal number
    """),
    md("## 5. Fees"),
    code('print(fees.estimate("TELECEL", "send_other_network", "40", date(2026, 9, 25)))'),
]

nb = nbformat.v4.new_notebook(cells=cells)
nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
NotebookClient(nb, timeout=120, resources={"metadata": {"path": str(HERE)}}).execute()
nbformat.write(nb, HERE / "demo.ipynb")
(HERE / "september_ledger.xlsx").unlink(missing_ok=True)
print("Wrote notebooks/demo.ipynb")
