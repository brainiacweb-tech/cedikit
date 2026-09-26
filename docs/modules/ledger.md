# Ledger

Only transactions that move wallet money are counted. Notices (e.g. "you have received airtime") go to `ledger.notices`, unknown messages to `ledger.unrecognised`, and repeated transaction IDs are dropped.

::: cedikit.ledger
