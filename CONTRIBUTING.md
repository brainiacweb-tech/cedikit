# Contributing to cedikit

Thanks for helping! A few ground rules keep the library trustworthy.

## Setup

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows; use `source .venv/bin/activate` elsewhere
pip install -e ".[dev]"
```

Before opening a pull request, all of these must pass:

```bash
pytest
pytest --no-cov --doctest-modules src
ruff check . && ruff format --check .
mypy
mkdocs build --strict         # needs pip install -e ".[docs]"
```

## Rules

- **Never commit real personal data.** Phone numbers, names, transaction IDs and balances in tests
  and fixtures must be fake. Anonymise SMS samples *before* they enter the repository with
  `cedikit sms anonymise messages.txt`, then read the output: anything marked `CHECK BY HAND`
  may still contain names.
- **Money is `Decimal`, never `float`.**
- **Data lives in data files.** Network prefixes, SMS templates, fee tables and scam phrases belong
  in YAML under `src/cedikit/`, not hard-coded in Python.
- **Be honest in outputs.** Network guesses are *likely*, fees are *estimates*, fraud results are
  *risk indicators*.
- Public functions get type hints and a Google-style docstring with an example.

## Updating fee tables and scam phrases

- Fee rules (`src/cedikit/fees/tables/*.yaml`) must cite their evidence in `source`: an official
  tariff or real (anonymised) messages. When charges change, add a new rule with a `from:` date
  rather than editing the old one, so historical transactions keep the old rate.
- New scam phrases (`src/cedikit/fraud/scam_phrases.yaml`) need a scam sample in
  `tests/fixtures/sample_messages/scam.yaml`, and all genuine fixtures must still score LOW.
  Check with `cedikit.evaluation.evaluate_fraud`.

## Updating network prefixes

Edit `src/cedikit/data/prefixes.yaml`, bump its `version` date, cite your source (e.g. the NCA
numbering plan) in the pull request, and add a test for the new prefix.
