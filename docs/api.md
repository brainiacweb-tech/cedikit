# Web API

cedikit can run as a small **web API**, so apps written in **any language** can use it:
JavaScript, PHP, Java, Kotlin (Android), Dart (Flutter), C#, Go and others. You send JSON
over HTTP and get JSON back.

```bash
pip install "cedikit[api]"
cedikit api
```

```text
cedikit API at http://127.0.0.1:8000 - documentation at /docs (Ctrl+C to stop)
```

Open **<http://127.0.0.1:8000/docs>** for interactive documentation. Every endpoint is
listed there with examples, and a **Try it out** button sends real requests. The
machine-readable OpenAPI schema is at `/openapi.json`, which you can use to generate a client
library for your language.

## Endpoints

All endpoints except `/` and `/health` take a JSON body sent with `POST`.

| Endpoint | Send | Get back |
|---|---|---|
| `GET /` · `GET /health` | nothing | Version and endpoint list · `{"status": "ok"}` |
| `POST /v1/phone/check` | `{"number": "024 412 3456", "style": "e164"}` | Valid or not, E.164, formatted, likely network, masked, reason if invalid |
| `POST /v1/phone/clean` | `{"numbers": ["0244123456", "244123456", …]}` | Counts plus one result per number (`valid`, `fixed` or `invalid`) |
| `POST /v1/money/parse` | `{"text": "GH₵1.2k"}` | `"1200.00"`, formatted, in words |
| `POST /v1/sms/parse` | `{"text": "…", "sender": "MobileMoney"}` | Type, amount, fee, tax, balance, counterparty, ID… |
| `POST /v1/fraud/check` | `{"text": "…", "sender": "0551234567", "history": […]}` | Risk (`LOW`/`MEDIUM`/`HIGH`), score, reasons, advice |
| `POST /v1/ledger` | `{"messages": ["…", "…"], "sender": "MobileMoney"}` | Totals, every transaction with a category, notes |
| `POST /v1/fees/estimate` | `{"network": "MTN", "kind": "cash_out", "amount": "500"}` | Fee, tax, total and where each number comes from |
| `POST /v1/ids/check` | `{"value": "GHA-123456789-0"}` | Valid or not, kind, masked, region and district |
| `POST /v1/screenshot` | A picture as `multipart/form-data` (field `image`) | Each message read from it, parsed and fraud-checked |

`style` is one of `e164`, `local`, `pretty` or `international`. `kind` is one of
`send_same_network`, `send_other_network`, `cash_out`, `cash_in`, `receive`, `airtime` or
`merchant` (see [Fees](modules/fees.md)). `sender`, `history`, `received_at` and
`on` are optional.

!!! important "Money is always a string"
    Amounts come back as strings such as `"1200.50"`, never as JSON numbers. Many languages
    turn JSON numbers into floating-point values, which cannot store `0.10` exactly. Keep
    amounts as strings, or convert them to your language's decimal type.

## Examples

A fake alert, checked from the command line:

```bash
curl -X POST http://127.0.0.1:8000/v1/fraud/check \
  -H "Content-Type: application/json" \
  -d '{"text": "Cash In for GHS150.00 from AKOSUA. Avaliable balan 640.35", "sender": "0551234567"}'
```

```json
{
  "risk": "HIGH",
  "score": 0.96,
  "headline": "Very likely fake",
  "reasons": [
    "Sent from a personal phone number (+233 55 123 4567), not an official sender ID such as MobileMoney or T-CASH. Genuine alerts never come from personal numbers.",
    "Looks like a Mobile Money alert but does not match any genuine message format.",
    "Contains spelling mistakes ('Avaliable', 'balan'). Genuine alerts are machine-generated and don't have typos."
  ],
  "checks": {"sender": false, "format": false, "spelling": false, "scam_phrases": true, "disguised_letters": true},
  "advice": "Before releasing goods or cash, confirm the payment in your official Mobile Money app ..."
}
```

=== "JavaScript"

    ```javascript
    const response = await fetch("http://127.0.0.1:8000/v1/phone/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ number: "024 412 3456" }),
    });
    const result = await response.json();
    console.log(result.e164, result.network); // +233244123456 MTN
    ```

=== "PHP"

    ```php
    $ch = curl_init("http://127.0.0.1:8000/v1/money/parse");
    curl_setopt_array($ch, [
        CURLOPT_POST => true,
        CURLOPT_HTTPHEADER => ["Content-Type: application/json"],
        CURLOPT_POSTFIELDS => json_encode(["text" => "GH₵1.2k"]),
        CURLOPT_RETURNTRANSFER => true,
    ]);
    $result = json_decode(curl_exec($ch), true);
    echo $result["amount"]; // 1200.00
    ```

=== "Python"

    ```python
    import requests

    with open("screenshot.png", "rb") as picture:
        result = requests.post("http://127.0.0.1:8000/v1/screenshot", files={"image": picture}).json()
    for message in result["messages"]:
        print(message["fraud"]["risk"], message["text"][:60])
    ```

    (In Python you can also `import cedikit` directly, without the API.)

=== "Dart (Flutter)"

    ```dart
    import 'dart:convert';
    import 'package:http/http.dart' as http;

    final response = await http.post(
      Uri.parse('http://10.0.2.2:8000/v1/fees/estimate'), // 10.0.2.2 = your PC, from the Android emulator
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'network': 'MTN', 'kind': 'cash_out', 'amount': '500'}),
    );
    final fee = jsonDecode(response.body)['fee']; // a string, e.g. "5.00"
    ```

## Errors

| Status | Meaning |
|---|---|
| `200` | Success. An invalid phone number or ID is still a `200`, with `"valid": false` and a reason. |
| `401` | An API key is required and was missing or wrong. |
| `413` | The picture is larger than 10 MB. |
| `422` | Something in the request is wrong, e.g. `"abc"` as an amount or an unknown network. `detail` says what. |
| `501` | Screenshots need an OCR engine that isn't installed. |

## Limits

- One message: up to 5,000 characters.
- One request: up to 5,000 messages or phone numbers.
- One picture: up to 10 MB.

## Privacy and security

- **Nothing is stored.** Each request is handled in memory and forgotten. The server does
  not log message text.
- **Local only by default.** `cedikit api` listens on `127.0.0.1`, so only your own computer
  can reach it.
- **To share it on a network** (e.g. to test from a phone on the same Wi-Fi), start it with
  `--host 0.0.0.0` and **set an API key**:

    ```bash
    # Windows PowerShell:  $env:CEDIKIT_API_KEY = "a-long-random-secret"
    export CEDIKIT_API_KEY="a-long-random-secret"
    cedikit api --host 0.0.0.0
    ```

    Every request (except `/` and `/health`) must then send the key in an `X-API-Key` header.
    cedikit warns you if you share the API without a key.
- **Browsers.** By default any website may call the API from a browser (CORS). To allow only
  your own site, set `CEDIKIT_API_CORS=https://your-site.example` (comma-separate several).
- **On the internet**, put it behind HTTPS (for example a reverse proxy such as Caddy or
  nginx). The API key travels in a header, so it must not be sent over plain HTTP.

## Hosting it yourself

The API is a standard [FastAPI](https://fastapi.tiangolo.com/) app at `cedikit.api:app`, so
any ASGI server can run it:

```bash
uvicorn cedikit.api:app --host 0.0.0.0 --port 8000 --workers 2
```

In your own Python code, `cedikit.api.create_app(api_key=..., cors_origins=[...])` builds an
app with your settings. You can mount it inside a larger FastAPI app.

!!! warning "Risk ratings are indicators"
    A `LOW` fraud risk does not guarantee a payment is real. Apps built on the API should tell
    users to confirm payments in the official Mobile Money app before releasing goods.
