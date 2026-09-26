# Fraud detection

Checks: sender ID, genuine format, spelling, scam phrases, disguised (accented) letters, transaction ID length, balance consistency, and an optional ML model. Signals combine with a noisy-OR: `score = 1 - (1 - s1)(1 - s2)...`. LOW < 0.35 <= MEDIUM <= 0.70 < HIGH.

!!! warning
    Results are risk indicators, not guarantees. Always confirm payments in the official app.

::: cedikit.fraud

::: cedikit.fraud.classifier
