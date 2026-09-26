# Quickstart

## Phone numbers

```python
from cedikit import phone

phone.normalise("024 412 3456")  # '+233244123456'
phone.format("+233244123456", "pretty")  # '024 412 3456'
phone.is_valid("02441234")  # False
phone.likely_network("0244123456").network  # 'MTN' (likely - numbers can be ported)
phone.mask("0244123456")  # '024****456'

report = phone.clean_column(["0244123456", "+233 50 123 4567", "12345"])
print(report)  # 3 numbers: 0 valid, 2 fixed, 1 invalid
```

## Money

```python
from cedikit import money, Cedi

money.parse("GH₵1.2k")  # Decimal('1200.00')
money.format("1200.5")  # 'GH₵ 1,200.50'
money.to_words("1200.50")  # 'One thousand two hundred Ghana cedis and fifty pesewas'
money.format(1200.5)  # CediTypeError: floats can't represent pesewas exactly

sum([Cedi("1.10"), Cedi("2.20")])  # Cedi('3.30') - exact
```

## MoMo SMS → ledger

```python
from cedikit import sms
from cedikit.ledger import Ledger

result = sms.parse(message_text, sender="MobileMoney")
if result.ok:
    tx = result.transaction
    print(tx.type, tx.amount, tx.counterparty, tx.balance, tx.confidence)

ledger = Ledger.from_messages(inbox_messages, sender="MobileMoney").categorise()
print(ledger.summary())
ledger.cash_flow("week")
ledger.top_counterparties(5, by="value")
ledger.balance_gaps()  # places where a message is probably missing
ledger.export("september.xlsx")  # Transactions, Summary, Cash flow, Categories
ledger.plot(path="cash_flow.png")
```

## Fake payment alerts

```python
from cedikit import fraud

report = fraud.check(message_text, sender="+233591234567", history=ledger.transactions)
print(report)
# Risk: HIGH (score 0.99)
# Reasons:
#   - Sent from a personal phone number (+233 59 123 4567), not an official sender ID ...
```

Always pass the sender when you have it: it is the strongest single signal.

## Fees

```python
from datetime import date
from cedikit import fees

print(fees.estimate("TELECEL", "send_other_network", "40.00", date(2026, 9, 25)))
```

## Command line

```bash
cedikit phone clean customers.csv --column phone
cedikit sms parse inbox.txt --sender MobileMoney --export xlsx
cedikit fraud check "Cash receive for 200.00 ..." --sender 0551234567
```

See [Command line](cli.md) for everything.
