# Adding an SMS template

Telcos change their message wording from time to time. When that happens, cedikit needs a new
template, not new code. Templates live in `src/cedikit/sms/templates/<network>.yaml`.

## 1. Anonymise the sample first

Before a message goes anywhere in the repository, replace **every** name, phone number, transaction
ID, amount, balance, reference and date with fake values. Keep everything else exactly as it is:
the wording, capital letters, punctuation, and even odd spacing like `NAME .` or double spaces.
Those quirks are what the template has to match.

## 2. Add a fixture

Append the anonymised message to `tests/fixtures/sample_messages/genuine.yaml` with the fields you
expect the parser to extract:

```yaml
- id: mtn_cash_out
  sender: MobileMoney
  text: |-
    Cash Out made for GHS40.00 to ADOM ELECTRICALS . Current Balance: GHS22.10 ...
  expected:
    template: mtn_cash_out
    type: CASH_OUT
    amount: "40.00"
    counterparty_name: ADOM ELECTRICALS
```

Run `pytest tests/test_sms_parser.py`. The new fixture should fail.

## 3. Write the template

```yaml
  - name: mtn_cash_out
    type: CASH_OUT            # RECEIVED SENT CASH_OUT CASH_IN MERCHANT AIRTIME BILL REVERSAL
    source: sample 2026-09    # where the format was seen
    pattern: >-
      Cash Out made for {{amount}} to {{counterparty_name}} ?\.
      Current Balance:? {{balance}}
      Financial Transaction Id: {{transaction_id}}\.
      .*?Fee charged: {{fee}}
    fields:
      transaction_id: '\d{11}'  # optional: tighter regex for one placeholder
```

How matching works:

- The message is **cleaned** first: whitespace (including line breaks) collapses to single spaces,
  and `GH₵`, `GH¢`, `GHC` and `₵` all become `GHS`. The `>-` block joins your lines with single
  spaces too, so write the pattern the way the cleaned message reads.
- **Keep optional groups on the same line as the text before them.** Each line break adds a
  space, so an optional group on its own line leaves a double space when it's absent. Write
  `Balance: {{balance}}\.(?: Reference: {{reference}}\.)?`, not the group on a new line.
- `pattern` is a regular expression that must match from the **start** of the message. Any text
  after it (adverts, safety tips) is ignored. Escape literal dots as `\.`.
- `{{placeholders}}` become named capture groups. Money placeholders (`amount`, `fee`, `tax`,
  `balance`, `available_balance`) already include the `GHS ?` prefix. The full list is
  `FIELD_PATTERNS` in `src/cedikit/sms/parser.py`.
- `extras` are fields that can appear anywhere, e.g. a `Reference:` after an advert:
  `reference: 'Reference: {{reference}} ?\.'`
- `affects_wallet: false` marks notices that repeat another transaction without moving wallet
  money, e.g. Telecel's "you have received airtime" after an airtime purchase (same transaction
  ID). They still parse, but ledgers and balance checks skip them.
- `optional` lists fields that are sometimes missing. Missing optional fields don't lower
  confidence.
- Confidence = (required fields found and valid ÷ required fields) × `weight`. Below 0.8, the
  transaction's `needs_review` is True.

## 4. Check

```bash
pytest
ruff check . && mypy
```

If you can't release yet, apps can load a template file at runtime:
`sms.Parser(extra_template_files=["my_templates.yaml"])`.
