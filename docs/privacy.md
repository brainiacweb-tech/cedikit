# Privacy and data

- **Offline only.** cedikit never makes network calls.
- **Nothing is stored** unless you export it yourself.
- **Masking helpers:** `phone.mask()` and `ids.ghana_card.mask()` for logs and reports.
- **No real personal data in the repository.** Every sample message is anonymised before it is
  committed. Use the anonymiser:

```bash
cedikit sms anonymise my_messages.txt --seed 1 > anonymised.txt
```

It replaces phone numbers (keeping the network prefix), transaction IDs (keeping their length),
amounts (all scaled by one factor, so balances still add up), dates (all shifted by one offset),
links, and - when the message format is recognised - names and references. Messages it cannot
parse are marked `CHECK BY HAND`, because names in them can't be found automatically.
**Always read the output before sharing it.**

- **Honest outputs.** Network detection says *likely*, fees are *estimates*, fraud results are
  *risk indicators*. Users should always confirm payments in their official app.
- **Responsible disclosure.** Scam rules are published to help the public. If you train the
  optional ML model, keep your own model and thresholds private.
- The design follows the principles of Ghana's Data Protection Act, 2012 (Act 843).
