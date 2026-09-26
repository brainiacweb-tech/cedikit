# cedikit

**A Python toolkit for Ghanaian phone numbers, cedi amounts, and Mobile Money transactions.**

[![PyPI](https://img.shields.io/pypi/v/cedikit)](https://pypi.org/project/cedikit/)
[![Docs](https://readthedocs.org/projects/cedikit/badge/?version=latest)](https://cedikit.readthedocs.io/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](https://github.com/brainiacweb-tech/cedikit/blob/main/LICENSE)

Every Ghanaian app ends up writing the same code: cleaning phone numbers typed five different
ways, adding up cedi amounts without floating-point errors, and making sense of MoMo SMS
alerts. cedikit does this once, carefully, with tests.

Everything runs **offline**. No user data leaves the device.

## Install

```bash
pip install cedikit            # core + the `cedikit` command
pip install "cedikit[all]"     # + pandas, Excel export, charts, ML, Pydantic, Django, Flask
```

Requires Python 3.10+.

## 30-second tour

```python
from cedikit import phone, money, sms, fraud, Cedi
from cedikit.ledger import Ledger

phone.normalise("024 412 3456")  # '+233244123456'
phone.likely_network("0244123456").network  # 'MTN' (likely - numbers can be ported)

money.parse("GH₵1.2k")  # Decimal('1200.00')
money.to_words("1200.50")  # 'One thousand two hundred Ghana cedis and fifty pesewas'
sum([Cedi("1.10"), Cedi("2.20")])  # Cedi('3.30') - exact, unlike 1.1 + 2.2

tx = sms.parse(message_text, sender="MobileMoney").transaction
tx.type, tx.amount, tx.counterparty, tx.balance

ledger = Ledger.from_messages(inbox, sender="MobileMoney").categorise()
print(ledger.summary())
ledger.export("september.xlsx")  # Transactions, Summary, Cash flow, Categories

print(fraud.check(suspicious_text, sender="+233591234567", history=ledger.transactions))
# Risk: HIGH (score 0.99)
# Reasons:
#   - Sent from a personal phone number (+233 59 123 4567), not an official sender ID ...
#   - Claimed balance GHS 640.35 does not follow from your last genuine balance ...
```

From the command line:

```bash
cedikit phone clean customers.csv --column phone
cedikit sms parse inbox.csv --export xlsx
cedikit fraud check "Cash receive for 200.00 ..." --sender 0551234567
```

## Modules

| Module | What it does |
|---|---|
| `cedikit.phone` | Normalise, validate, format, mask, likely network, bulk clean |
| `cedikit.money` | `Decimal` parsing, formatting, words, rounding, the `Cedi` type |
| `cedikit.sms` | MTN MoMo and Telecel Cash SMS → transactions (12 formats); anonymiser |
| `cedikit.fraud` | Fake-alert detection with reasons; optional ML classifier |
| `cedikit.ledger` | Summary, cash flow, categories, balance gaps, CSV/Excel/JSON, charts |
| `cedikit.fees` | Fee and E-Levy estimates from dated, sourced tables |
| `cedikit.ids` | Ghana Card and GhanaPostGPS format checks |
| `cedikit.evaluation` | Parser accuracy and fraud precision/recall on labelled data |
| Integrations | pandas accessor, Pydantic types, Django and Flask validators |

Full documentation: [the docs site](https://cedikit.readthedocs.io/). The end-to-end demo is
[notebooks/demo.ipynb](https://github.com/brainiacweb-tech/cedikit/blob/main/notebooks/demo.ipynb), using the data in [examples/](https://github.com/brainiacweb-tech/cedikit/tree/main/examples).

## Honest outputs

- **Network detection is only "likely".** Mobile number portability lets people keep their number
  when they switch networks.
- **Fees are estimates.** The tables record only charges seen in real messages or published
  rules, each with its source. Unknown charges are reported as unknown, never guessed.
- **Fraud results are risk indicators, not guarantees.** Always confirm a payment in the official
  Mobile Money app before releasing goods.
- **Money is never a float.**

## Development

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows; use `source .venv/bin/activate` elsewhere
pip install -e ".[dev,docs]"
pytest                        # tests + coverage (>= 90%)
pytest --no-cov --doctest-modules src
ruff check . && ruff format --check .
mypy
mkdocs serve                  # docs at http://127.0.0.1:8000
```

See [CONTRIBUTING.md](https://github.com/brainiacweb-tech/cedikit/blob/main/CONTRIBUTING.md) and [Adding an SMS template](https://github.com/brainiacweb-tech/cedikit/blob/main/docs/contributing-templates.md).

## Licence

MIT © Francis Kusi. Built in Ghana, for Ghana.
