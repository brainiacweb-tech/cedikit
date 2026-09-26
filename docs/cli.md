# Command line

Installing cedikit adds a `cedikit` command. Run `cedikit --help` or `cedikit <group> --help`.

| Command | What it does |
|---|---|
| `cedikit phone clean FILE.csv --column phone [--style pretty] [--output OUT.csv]` | Normalise a column; adds `_status` and `_note` columns |
| `cedikit phone check NUMBER` | Formats and likely network of one number |
| `cedikit money parse TEXT` | `GH₵1.2k` → `1200.00` |
| `cedikit money words AMOUNT` | Amount in words |
| `cedikit sms parse FILE [--sender ID] [--export csv\|xlsx\|json] [--output PATH]` | Messages → ledger summary, balance gaps, export |
| `cedikit sms anonymise FILE [--seed N]` | Anonymise messages before sharing them |
| `cedikit fraud check TEXT [--sender ID]` | Risk rating with reasons (`-` reads the text from stdin) |
| `cedikit fees estimate NETWORK KIND AMOUNT [--on YYYY-MM-DD]` | Fee and E-Levy estimate |
| `cedikit ids check VALUE` | Ghana Card or GhanaPostGPS format check |

**Message files** for `sms parse` and `sms anonymise` are either plain text with one message per
paragraph (messages separated by a blank line), or a CSV with a `text` column.

Try it on the demo data in `examples/`:

```bash
cedikit phone clean examples/customers.csv --column phone
cedikit sms parse examples/inbox.txt --export xlsx
```
