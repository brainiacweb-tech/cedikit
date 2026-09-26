# cedikit

**A Python toolkit for Ghanaian phone numbers, cedi amounts and Mobile Money transactions.**

Almost every Ghanaian digital product handles the same data: phone numbers typed five different
ways, cedi amounts, and Mobile Money (MoMo) SMS alerts. cedikit handles them once, carefully,
with tests.

```bash
pip install cedikit            # core + command line
pip install "cedikit[all]"     # + pandas, Excel, charts, ML, Pydantic, Django, Flask
```

| Module | What it does |
|---|---|
| [`phone`](modules/phone.md) | Normalise, validate, format and mask numbers; guess the network |
| [`money`](modules/money.md) | Exact `Decimal` parsing, formatting, words and the float-proof `Cedi` type |
| [`sms`](modules/sms.md) | MTN MoMo and Telecel Cash SMS → structured transactions; anonymiser |
| [`fraud`](modules/fraud.md) | Rates payment SMS as LOW / MEDIUM / HIGH risk and explains why |
| [`ledger`](modules/ledger.md) | Summaries, cash flow, categories, balance gaps, Excel/CSV/JSON export, charts |
| [`fees`](modules/fees.md) | Fee and E-Levy estimates from dated, sourced tables |
| [`ids`](modules/ids.md) | Ghana Card and GhanaPostGPS format checks |
| [Integrations](modules/integrations.md) | pandas accessor, Pydantic types, Django and Flask validators |

## Principles

- **Offline.** No network calls anywhere. No data leaves the device.
- **Honest outputs.** Networks are *likely* (numbers can be ported), fees are *estimates*, fraud
  results are *risk indicators*. Unknown values are reported as unknown, never guessed.
- **Money is never a float.**
- **Data lives in data files.** Prefixes, SMS templates, fee tables and scam phrases are YAML, so
  they can be updated without code changes.

!!! warning "Always confirm payments"
    No SMS check can prove a payment is real. Before releasing goods, confirm the payment in your
    official Mobile Money app or through your network's official USSD menu.

*Built in Ghana, for Ghana.*
