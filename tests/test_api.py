"""Tests for the web API (cedikit.api)."""

from collections.abc import Iterator
from typing import Any

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("multipart")

from fastapi.testclient import TestClient

from cedikit import __version__, ocr
from cedikit.api import MAX_IMAGE, create_app
from cedikit.app import common
from cedikit.ledger import split_messages

GENUINE, GENUINE_SENDER = common.EXAMPLES["Genuine MTN payment"]
FAKE, _ = common.EXAMPLES["Fake cash-in"]


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(create_app(api_key="")) as c:
        yield c


def post(client: TestClient, path: str, body: dict[str, Any]) -> Any:
    response = client.post(path, json=body)
    assert response.status_code == 200, response.text
    return response.json()


# -- about --------------------------------------------------------------------------------


def test_about_lists_every_endpoint(client: TestClient) -> None:
    info = client.get("/").json()
    assert info["version"] == __version__ and info["docs"] == "/docs"
    assert "/v1/fraud/check" in info["endpoints"] and "/v1/screenshot" in info["endpoints"]
    assert client.get("/health").json() == {"status": "ok"}


def test_interactive_docs_are_served(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    assert schema["info"]["title"] == "cedikit API"
    assert "/v1/ledger" in schema["paths"]


# -- phone --------------------------------------------------------------------------------


def test_phone_check_valid(client: TestClient) -> None:
    out = post(client, "/v1/phone/check", {"number": "024 412 3456", "style": "international"})
    assert out["valid"] and out["e164"] == "+233244123456"
    assert out["formatted"] == "+233 24 412 3456"
    assert out["network"] == "MTN" and out["masked"] == "024****456"


def test_phone_check_invalid_is_not_an_error(client: TestClient) -> None:
    out = post(client, "/v1/phone/check", {"number": "12"})
    assert not out["valid"] and out["e164"] is None and "9 digits" in out["reason"]


def test_phone_clean(client: TestClient) -> None:
    out = post(client, "/v1/phone/clean", {"numbers": ["+233244123456", "244123456", "x"]})
    assert (out["total"], out["valid"], out["fixed"], out["invalid"]) == (3, 1, 1, 1)
    assert [r["status"] for r in out["results"]] == ["valid", "fixed", "invalid"]
    assert out["results"][1]["e164"] == "+233244123456"
    assert out["results"][2]["network"] is None


# -- money --------------------------------------------------------------------------------


def test_money_is_returned_as_exact_strings(client: TestClient) -> None:
    out = post(client, "/v1/money/parse", {"text": "GH₵1.2k"})
    assert out == {
        "amount": "1200.00",
        "formatted": "GH₵ 1,200.00",
        "formatted_code": "GHS 1,200.00",
        "words": "One thousand two hundred Ghana cedis",
    }


def test_bad_amount_is_a_422_with_a_reason(client: TestClient) -> None:
    response = client.post("/v1/money/parse", json={"text": "abc"})
    assert response.status_code == 422 and "abc" in response.json()["detail"]


# -- sms and fraud ------------------------------------------------------------------------


def test_sms_parse(client: TestClient) -> None:
    out = post(client, "/v1/sms/parse", {"text": GENUINE, "sender": GENUINE_SENDER})
    tx = out["transaction"]
    assert out["status"] == "parsed" and tx["type"] == "RECEIVED" and tx["direction"] == "in"
    assert tx["amount"] == "50.00" and tx["balance"] == "80.00" and tx["tax"] is None
    assert tx["counterparty"]["name"] == "KOFI MENSAH" and tx["affects_wallet"]


def test_sms_parse_unrecognised(client: TestClient) -> None:
    out = post(client, "/v1/sms/parse", {"text": "Hello, how are you?"})
    assert out == {"status": "unrecognised", "transaction": None}


def test_sms_parse_uses_received_at(client: TestClient) -> None:
    body = {"text": GENUINE, "received_at": "2026-09-20T10:30:00+00:00"}
    tx = post(client, "/v1/sms/parse", body)["transaction"]
    assert tx["timestamp"].startswith("2026-09-20")


def test_fraud_check_flags_fake(client: TestClient) -> None:
    out = post(client, "/v1/fraud/check", {"text": FAKE, "sender": "0551234567"})
    assert out["risk"] == "HIGH" and out["headline"] == "Very likely fake"
    assert not out["checks"]["sender"] and out["reasons"] and "official" in out["advice"]


def test_fraud_check_genuine_with_history(client: TestClient) -> None:
    earlier = GENUINE.replace("GHS 80.00", "GHS 30.00").replace("51234567890", "51234567889")
    body = {"text": GENUINE, "sender": GENUINE_SENDER, "history": [{"text": earlier}]}
    out = post(client, "/v1/fraud/check", body)
    assert out["risk"] == "LOW" and out["checks"]["sender"]


def test_empty_text_is_rejected(client: TestClient) -> None:
    assert client.post("/v1/fraud/check", json={"text": ""}).status_code == 422


def test_oversized_text_is_rejected(client: TestClient) -> None:
    assert client.post("/v1/sms/parse", json={"text": "x" * 5001}).status_code == 422


# -- ledger -------------------------------------------------------------------------------


def test_ledger(client: TestClient) -> None:
    messages = [*split_messages(common.SAMPLE_MESSAGES), {"text": "Hi"}]
    out = post(client, "/v1/ledger", {"messages": messages, "sender": "MobileMoney"})
    summary = out["summary"]
    assert summary["transactions"] == 6 and summary["total_in"] == "245.00"
    assert summary["closing_balances"] == {"MTN": "94.00"}
    assert out["unrecognised"] == 1 and any("not recognised" in n for n in out["notes"])
    assert out["transactions"][4]["category"] == "loan repayment"
    assert all(isinstance(v, str) for v in out["category_totals"].values())


def test_ledger_without_categories(client: TestClient) -> None:
    body = {"messages": [GENUINE], "sender": GENUINE_SENDER, "categorise": False}
    out = post(client, "/v1/ledger", body)
    assert out["category_totals"] == {} and out["transactions"][0]["category"] is None


def test_ledger_needs_messages(client: TestClient) -> None:
    assert client.post("/v1/ledger", json={"messages": []}).status_code == 422


# -- fees and ids -------------------------------------------------------------------------


def test_fee_estimate(client: TestClient) -> None:
    body = {"network": "telecel", "kind": "send_other_network", "amount": "40", "on": "2026-09-25"}
    out = post(client, "/v1/fees/estimate", body)
    assert (out["network"], out["fee"], out["tax"], out["total"]) == (
        "TELECEL",
        "0.20",
        "0.00",
        "0.20",
    )
    assert out["known"] and out["is_estimate"] and out["basis"]


def test_fee_estimate_unknown_network_is_422(client: TestClient) -> None:
    response = client.post(
        "/v1/fees/estimate", json={"network": "glo", "kind": "cash_out", "amount": "40"}
    )
    assert response.status_code == 422 and "GLO" in response.json()["detail"]


def test_fee_estimate_unknown_kind_is_422(client: TestClient) -> None:
    body = {"network": "MTN", "kind": "teleport", "amount": "40"}
    assert client.post("/v1/fees/estimate", json=body).status_code == 422


@pytest.mark.parametrize(
    ("value", "kind", "extra"),
    [
        ("GHA-123456789-0", "ghana_card", {"card_type": "citizen", "masked": "GHA-12*****89-0"}),
        ("AK-039-5028", "digital_address", {"region": "Ashanti"}),
    ],
)
def test_id_check_valid(client: TestClient, value: str, kind: str, extra: dict[str, str]) -> None:
    out = post(client, "/v1/ids/check", {"value": value})
    assert out["valid"] and out["kind"] == kind and out["normalised"] == value
    assert extra.items() <= out.items()


def test_id_check_invalid(client: TestClient) -> None:
    out = post(client, "/v1/ids/check", {"value": "nope"})
    assert not out["valid"] and out["kind"] == "unknown" and "Ghana Card" in out["message"]


# -- screenshots --------------------------------------------------------------------------


def upload(client: TestClient, data: bytes, **params: Any) -> Any:
    return client.post(
        "/v1/screenshot", files={"image": ("s.png", data, "image/png")}, params=params
    )


@pytest.mark.skipif(ocr.available_engine() is None, reason="no OCR engine installed")
def test_screenshot(client: TestClient) -> None:
    response = upload(client, common.sample_screenshot())
    assert response.status_code == 200, response.text
    out = response.json()
    assert out["sender"] == "MobileMoney" and len(out["messages"]) >= 2
    first = out["messages"][0]
    assert first["parsed"]["status"] == "parsed" and first["fraud"]["risk"] == "LOW"


@pytest.mark.skipif(ocr.available_engine() is None, reason="no OCR engine installed")
def test_screenshot_without_fraud_check(client: TestClient) -> None:
    out = upload(client, common.sample_screenshot(), check=False).json()
    assert all(m["fraud"] is None for m in out["messages"])


def test_screenshot_rejects_non_images(client: TestClient) -> None:
    response = upload(client, b"not a picture")
    assert response.status_code == 422 and "PNG" in response.json()["detail"]


def test_screenshot_rejects_huge_files(client: TestClient) -> None:
    assert upload(client, b"\0" * (MAX_IMAGE + 1)).status_code == 413


def test_screenshot_without_ocr_is_501(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable(_image: object) -> None:
        raise ocr.OcrUnavailable("no engine")

    monkeypatch.setattr(ocr, "read_screenshot", unavailable)
    assert upload(client, b"x").status_code == 501


# -- security -----------------------------------------------------------------------------


def test_api_key_is_required_when_set() -> None:
    with TestClient(create_app(api_key="s3cret")) as c:
        body = {"text": "GHS 5"}
        assert c.post("/v1/money/parse", json=body).status_code == 401
        wrong = c.post("/v1/money/parse", json=body, headers={"X-API-Key": "nope"})
        assert wrong.status_code == 401
        ok = c.post("/v1/money/parse", json=body, headers={"X-API-Key": "s3cret"})
        assert ok.status_code == 200
        assert c.get("/health").status_code == 200  # health checks stay open


def test_api_key_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CEDIKIT_API_KEY", "envkey")
    with TestClient(create_app()) as c:
        assert c.post("/v1/money/parse", json={"text": "5"}).status_code == 401


def test_cors_origins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CEDIKIT_API_CORS", "https://shop.example")
    with TestClient(create_app(api_key="")) as c:
        headers = {"Origin": "https://shop.example", "Access-Control-Request-Method": "POST"}
        allowed = c.options("/v1/money/parse", headers=headers)
        assert allowed.headers["access-control-allow-origin"] == "https://shop.example"
        headers["Origin"] = "https://evil.example"
        blocked = c.options("/v1/money/parse", headers=headers)
        assert "access-control-allow-origin" not in blocked.headers


# -- the `cedikit api` command ------------------------------------------------------------


def test_cli_starts_the_server(monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    from cedikit import cli

    calls: list[dict[str, Any]] = []
    monkeypatch.setattr("uvicorn.run", lambda app, **kw: calls.append({"app": app, **kw}))
    monkeypatch.delenv("CEDIKIT_API_KEY", raising=False)
    runner = CliRunner()

    local = runner.invoke(cli.app, ["api", "--port", "8100"])
    assert local.exit_code == 0 and "127.0.0.1:8100" in local.output
    assert "Warning" not in local.output
    assert calls[0] == {
        "app": "cedikit.api:app",
        "host": "127.0.0.1",
        "port": 8100,
        "log_level": "warning",
    }

    shared = runner.invoke(cli.app, ["api", "--host", "0.0.0.0"])
    assert shared.exit_code == 0 and "CEDIKIT_API_KEY" in shared.output

    monkeypatch.setattr("importlib.util.find_spec", lambda _name: None)
    missing = runner.invoke(cli.app, ["api"])
    assert missing.exit_code == 1 and "cedikit[api]" in missing.output
