# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/). Data-file updates (prefixes, templates, fee tables)
are released as patch versions.

## [Unreleased]

## [1.2.0] - 2026-09-26

The first PyPI release with the apps: it also brings the 1.1.0 features (desktop app, web app,
`python -m cedikit`), which were published on GitHub only.

### Added
- **Screenshots**: `cedikit.ocr.read_screenshot()` reads MoMo messages and the sender straight
  from a screenshot, offline (Windows' built-in OCR on Windows, RapidOCR elsewhere; extra
  `cedikit[ocr]`). It drops phone clutter (clock, "Sender can't accept replies"...), splits
  chat bubbles into separate messages, fixes common OCR slips (`GHS50.OO` -> `GHS50.00`) and
  reads the text at a better size when phones use large fonts.
- Apps: **"Open screenshot..."** and **"Try a sample screenshot"** in *Check a message* (with a
  picker when a picture holds several messages, and the sender filled in automatically), and
  **"Open screenshots..."** / screenshot upload in *Account book*.
- The stand-alone `.exe` includes screenshot reading and self-tests it.

## [1.1.0] - 2026-09-26

Published as a GitHub Release (with `cedikit-app.exe`); not uploaded to PyPI.

### Added
- **Desktop app** (`cedikit app` / `cedikit-app`), built with Tkinter: tabs to check a
  message for fraud, build an account book and save it to Excel/CSV, clean phone numbers,
  write amounts in words, estimate fees, and check Ghana Card numbers and GhanaPostGPS
  addresses. Sharp on high-resolution screens; "Try with samples" buttons throughout.
- **Stand-alone Windows program** `cedikit-app.exe` (no Python needed), built by
  `packaging/build_exe.py`, which also self-tests the result.
- **Web app** (`cedikit web`, extra `cedikit[web]`), built with Streamlit: the same tabs in
  the browser, served on localhost only, with Streamlit's usage statistics switched off.
- `cedikit.app.common`: shared labels, tables and examples, so both apps always agree.
- `python -m cedikit` works like the `cedikit` command.
- `ledger.read_messages()` and `ledger.split_messages()` (moved from the CLI).

### Removed
- Glo (023) numbers are no longer accepted by `cedikit.phone`; supported networks are MTN,
  Telecel and AT.

## [1.0.0] - 2026-09-26

First complete release, published on PyPI (https://pypi.org/project/cedikit/). Everything
runs offline.

### Added
- **`cedikit.phone`**: `normalise`, `is_valid`, `format` (e164 / local / pretty /
  international), `likely_network`, `mask`, `clean_column`. Prefix data in `data/prefixes.yaml`.
- **`cedikit.money`**: `parse`, `format` (symbol / code / compact), `to_words`,
  `round_pesewas` and the float-proof `Cedi` type.
- **`cedikit.sms`**: template-driven parser for MTN MoMo and Telecel Cash returning a
  `ParseResult` with a `Transaction` and confidence score; unrecognised messages never raise.
  12 templates built from real messages: Telecel send (same / other network), receive (same /
  other network), cash in, airtime purchase, airtime notice; MTN payment received, payment to
  merchants and loans, cash in, cash out, send to another network, data bundle.
  `Transaction.affects_wallet` marks notices that repeat a transaction. `sms.Parser` loads extra
  template files at runtime.
- **`cedikit.sms.anonymise`**: replaces names, numbers, IDs, amounts, dates and links while
  keeping wording and keeping balances consistent across a batch.
- **`cedikit.fraud`**: `check()` returns a `FraudReport` (risk, score, reasons, per-check
  results, advice). Checks: sender ID, genuine format, spelling, scam phrases, accented-letter
  disguises, transaction ID length, balance consistency; optional `ScamClassifier` (scikit-learn).
  Signals combine with a noisy-OR. Scam phrases live in `fraud/scam_phrases.yaml`.
- **`cedikit.ledger`**: `Ledger.from_messages` / `from_csv`, `summary`, `cash_flow`,
  `top_counterparties`, rule-based `categorise`, `category_totals`, `balance_gaps`, export to
  CSV / Excel / JSON, `to_dataframe`, `plot`.
- **`cedikit.fees`**: fee and E-Levy estimates from dated tables in which every rule cites its
  evidence; unknown values are `None`.
- **`cedikit.ids`**: Ghana Card format checks for `GHA` (citizens) and `FGN` (foreign
  nationals) with `card_type()`; GhanaPostGPS parsing with region and district names (218
  district codes, including digit codes such as `A2`), sourced from ghanapostgps.com and the
  Wikipedia postcode table.
- **`cedikit.evaluation`**: parser accuracy and fraud precision / recall on labelled files.
- **Integrations**: pandas `.cedikit` accessor, Pydantic types, Django validators, WTForms
  validators.
- **CLI** (`cedikit`): `phone clean|check`, `money parse|words`, `sms parse|anonymise`,
  `fraud check`, `fees estimate`, `ids check`.
- Docs site (MkDocs, hosted on Read the Docs), demo notebook, demo data generator,
  anonymised fixtures.

### Notes
- AT Money is out of scope (little used); AT numbers are still handled by `cedikit.phone`.
- Data checked against sources on 2026-09-26: E-Levy repeal date (2 April 2025, GRA);
  network prefixes (NCA numbering plan + later MTN assignments); MTN cash-out
  and same-network send schedules (third-party tracker, consistent with real messages).
- Still unconfirmed: MTN cross-network fee, Telecel cash-out fee (the only published table
  contradicts real messages), and district names against GhanaPostGPS's official table.
- The Ghana Card check digit is not validated: its algorithm is not published.
