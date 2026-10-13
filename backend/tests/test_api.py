"""API, auth, API-key, device, AI and simulator tests."""
import json
import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.core.crypto import decrypt_secret
from app.core.logging import JsonFormatter, redact
from app.models import AIProvider, ApiKey, AuditLog
from app.services.ai import providers as ai

# ----------------------------------------------------------------------------- auth


def test_requires_login(client):
    r = client.get("/api/v1/portfolios")
    assert r.status_code == 401
    assert r.json() == {"error": {"status": 401, "message": "Not authenticated"}}


def test_login_logout_and_revocation(client):
    bad = client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
    assert bad.status_code == 401
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "correct-horse-battery"})
    assert r.status_code == 200
    assert client.get("/api/v1/auth/me").json()["username"] == "admin"
    csrf = r.json()["csrf_token"]
    assert client.post("/api/v1/auth/logout").status_code == 403  # missing CSRF
    assert client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


def test_revoked_session_token_rejected_even_if_replayed(client):
    client.post("/api/v1/auth/login", json={"username": "admin", "password": "correct-horse-battery"})
    token = client.cookies.get("ls_session")
    csrf = client.cookies.get("ls_csrf")
    client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})
    client.cookies.set("ls_session", token)
    assert client.get("/api/v1/auth/me").status_code == 401


def test_csrf_required_for_mutations(admin):
    r = admin.c.post("/api/v1/portfolios", json={"name": "X"})
    assert r.status_code == 403
    assert admin.post("/api/v1/portfolios", json={"name": "X"}).status_code == 201


def test_login_rate_limited(client):
    codes = [client.post("/api/v1/auth/login", json={"username": "a", "password": "b"}).status_code for _ in range(12)]
    assert codes[-1] == 429 and 401 in codes


def test_failed_login_audited(client, db):
    client.post("/api/v1/auth/login", json={"username": "mallory", "password": "x"})
    assert db.query(AuditLog).filter_by(action="login_failed", actor="mallory").count() == 1


def test_openapi_and_error_shape(client):
    spec = client.get("/api/openapi.json").json()
    for path in ("/api/v1/device/dashboard", "/api/v1/device/heartbeat", "/api/v1/portfolios/{pid}/transactions",
                 "/api/v1/ai/providers/{pid}/test", "/api/v1/simulator/config"):
        assert path in spec["paths"], path
    about = client.get("/api/v1/about").json()
    assert about["owner"]["name"] == "Lalit Nayyar" and "not financial advice" in about["disclaimer"]


def test_validation_error_shape(admin):
    r = admin.post("/api/v1/portfolios", json={"name": ""})
    assert r.status_code == 422 and r.json()["error"]["message"] == "Validation failed"


# ----------------------------------------------------------------------------- portfolio flow

def _setup_portfolio(admin):
    aapl = admin.post("/api/v1/stocks", json={"ticker": "aapl"}).json()
    emaar = admin.post("/api/v1/stocks", json={"ticker": "EMAAR.AE"}).json()
    assert aapl["ticker"] == "AAPL" and aapl["data_quality"] == "ok" and emaar["currency"] == "AED"
    pf = admin.post("/api/v1/portfolios", json={"name": "Main", "base_currency": "USD"}).json()
    base = f"/api/v1/portfolios/{pf['id']}/transactions"
    for body in (
        {"type": "BUY", "stock_id": aapl["id"], "trade_date": "2026-01-02", "quantity": "10", "price": "150", "fees": "1"},
        {"type": "BUY", "stock_id": aapl["id"], "trade_date": "2026-02-02", "quantity": "10", "price": "170", "fees": "1"},
        {"type": "SELL", "stock_id": aapl["id"], "trade_date": "2026-03-02", "quantity": "5", "price": "180", "fees": "1"},
        {"type": "BUY", "stock_id": emaar["id"], "trade_date": "2026-03-03", "quantity": "1000", "price": "8", "fees": "0"},
    ):
        r = admin.post(base, json=body)
        assert r.status_code == 201, r.text
    admin.post("/api/v1/market/refresh")
    return pf, aapl, emaar


def test_portfolio_summary_with_fx_and_average_cost(admin):
    pf, aapl, _ = _setup_portfolio(admin)
    s = admin.get(f"/api/v1/portfolios/{pf['id']}/summary").json()
    h = {r["ticker"]: r for r in s["holdings"]}
    assert h["AAPL"]["quantity"] == "15"
    assert h["AAPL"]["avg_cost"] == "160.1000"         # (1501 + 1701) / 20
    assert h["AAPL"]["cost_basis"] == "2401.50"
    assert h["AAPL"]["realized_pl"] == "98.50"         # 900 - 1 - 800.5
    # EMAAR 1000 * 8.42 AED / 3.6725 (inverse of the seeded USDAED=X fixture quote)
    assert h["EMAAR.AE"]["market_value_base"] == "2292.72"
    assert s["accounting"] == "average-cost" and s["totals"]["active_holdings"] == 2
    assert abs(sum(float(x["allocation_pct"]) for x in s["holdings"]) - 100) < 0.02


def test_ledger_violation_rejected(admin):
    pf, aapl, _ = _setup_portfolio(admin)
    r = admin.post(f"/api/v1/portfolios/{pf['id']}/transactions",
                   json={"type": "SELL", "stock_id": aapl["id"], "trade_date": "2026-04-01", "quantity": "999", "price": "1"})
    assert r.status_code == 422 and "exceeds holding" in r.json()["error"]["message"]
    r = admin.post(f"/api/v1/portfolios/{pf['id']}/transactions",
                   json={"type": "ADJUSTMENT", "stock_id": aapl["id"], "trade_date": "2026-04-01", "quantity": "1"})
    assert r.status_code == 422


def test_unsupported_symbol_rejected(admin):
    r = admin.post("/api/v1/stocks", json={"ticker": "ZZZZ.XX"})
    assert r.status_code == 422 and "Unsupported symbol" in r.json()["error"]["message"]
    assert admin.post("/api/v1/stocks", json={"ticker": "bad symbol!"}).status_code == 422
    v = admin.post("/api/v1/stocks/validate", json={"ticker": "ZZZZ.XX"}).json()
    assert v["valid"] is False and "suffix" in v["hint"]


# ----------------------------------------------------------------------------- api keys + device

def _device_with_key(admin, pf_id=None, scopes=None, expires=365):
    dev = admin.post("/api/v1/devices", json={"device_uid": "LS-001", "name": "Desk", "portfolio_id": pf_id}).json()
    body = {"name": "desk key", "device_id": dev["id"], "expires_in_days": expires}
    if scopes:
        body["scopes"] = scopes
    k = admin.post("/api/v1/api-keys", json=body).json()
    return dev, k


def test_api_key_shown_once_hashed_and_scoped(admin, db, caplog):
    pf, *_ = _setup_portfolio(admin)
    dev, k = _device_with_key(admin, pf["id"])
    full = k["key"]
    assert full.startswith("lsk_") and len(full) > 40
    listed = admin.get("/api/v1/api-keys").text
    assert full not in listed and "****" in listed
    row = db.query(ApiKey).one()
    assert full not in row.key_hash and len(row.key_hash) == 64
    hdr = {"Authorization": f"Bearer {full}"}
    with caplog.at_level(logging.INFO):
        r = admin.c.get("/api/v1/device/dashboard", headers=hdr)
    assert r.status_code == 200, r.text
    dash = r.json()
    assert dash["device"]["id"] == "LS-001" and len(dash["pages"]) >= 2
    assert full not in caplog.text
    # 304 when unchanged
    assert admin.c.get(f"/api/v1/device/dashboard?since={dash['data_version']}", headers=hdr).status_code == 304
    # heartbeat
    hb = admin.c.post("/api/v1/device/heartbeat", headers=hdr, json={
        "firmware": "1.0.0", "rssi": -60, "uptime_s": 100, "api_status": "OK", "page": 1, "pages": 3,
        "rotation_enabled": True, "requested_s": 10, "effective_s": 60, "panel_profile": "JD79667_GDEY029F51H"})
    assert hb.status_code == 200
    d = admin.get("/api/v1/devices").json()[0]
    assert d["online"] and d["refresh_check"]["effective_s"] == 60 and d["refresh_check"]["clamped"]
    logs = admin.get(f"/api/v1/api-keys/{k['id']}/logs").json()
    assert len(logs) >= 3 and all("lsk_" not in json.dumps(x) for x in logs)


def test_api_key_scope_revoke_expiry_rotate(admin, db):
    dev, k = _device_with_key(admin, scopes=["device:heartbeat"])
    hdr = {"Authorization": f"Bearer {k['key']}"}
    assert admin.c.get("/api/v1/device/dashboard", headers=hdr).status_code == 403
    assert admin.c.get("/api/v1/device/dashboard", headers={"Authorization": "Bearer lsk_deadbeef_nope"}).status_code == 401
    assert admin.c.get("/api/v1/device/dashboard").status_code == 401
    # rotate: old key revoked, new key works
    rot = admin.post(f"/api/v1/api-keys/{k['id']}/rotate").json()
    assert rot["key"] != k["key"] and rot["rotated_from_id"] == k["id"]
    assert admin.c.post("/api/v1/device/heartbeat", headers=hdr, json={}).status_code == 401
    new_hdr = {"Authorization": f"Bearer {rot['key']}"}
    assert admin.c.post("/api/v1/device/heartbeat", headers=new_hdr, json={}).status_code == 200
    # revoke
    admin.post(f"/api/v1/api-keys/{rot['id']}/revoke")
    assert admin.c.post("/api/v1/device/heartbeat", headers=new_hdr, json={}).status_code == 401
    # expiry
    _, k2 = None, admin.post("/api/v1/api-keys", json={"name": "exp", "device_id": dev["id"],
                                                       "scopes": ["device:heartbeat"]}).json()
    row = db.get(ApiKey, k2["id"])
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    r = admin.c.post("/api/v1/device/heartbeat", headers={"Authorization": f"Bearer {k2['key']}"}, json={})
    assert r.status_code == 401 and "expired" in r.json()["error"]["message"]
    assert admin.post("/api/v1/api-keys", json={"name": "x", "scopes": ["admin:all"]}).status_code == 422


def test_device_rate_limited(admin):
    admin.put("/api/v1/settings", json={"device_rate_limit_per_min": 3})
    _, k = _device_with_key(admin)
    hdr = {"Authorization": f"Bearer {k['key']}"}
    codes = [admin.c.post("/api/v1/device/heartbeat", headers=hdr, json={}).status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200] and codes[3] == 429


def test_unbound_key_cannot_read_dashboard(admin):
    k = admin.post("/api/v1/api-keys", json={"name": "loose"}).json()
    r = admin.c.get("/api/v1/device/dashboard", headers={"Authorization": f"Bearer {k['key']}"})
    assert r.status_code == 403


# ----------------------------------------------------------------------------- AI

def _mock_transport(model_list=("gpt-test",), status=200):
    def handler(request: httpx.Request):
        assert request.headers.get("authorization") == "Bearer sk-test-secret-123456"
        if request.url.path.endswith("/models"):
            return httpx.Response(status, json={"data": [{"id": m} for m in model_list]} if status == 200
                                  else {"error": {"message": "Incorrect API key provided"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})
    return httpx.MockTransport(handler)


def test_ai_test_connection_success_and_failures():
    cfg = ai.AIConfig("openai", "https://api.example.test/v1", "gpt-test", "sk-test-secret-123456")
    ok = ai.test_connection(cfg, transport=_mock_transport())
    assert ok["ok"] and ok["latency_ms"] is not None and "model available" in ok["steps"]
    missing = ai.test_connection(cfg, transport=_mock_transport(model_list=("other",)))
    assert not missing["ok"] and "not available" in missing["message"]
    bad = ai.test_connection(cfg, transport=_mock_transport(status=401))
    assert not bad["ok"] and "401" in bad["message"]
    nokey = ai.test_connection(ai.AIConfig("deepseek", "https://x", "m", None))
    assert not nokey["ok"] and "requires an API key" in nokey["message"]


def test_ai_chat_token_limit_parameter():
    sent = []

    def handler(request: httpx.Request):
        body = json.loads(request.content)
        sent.append(body)
        if "max_tokens" in body and len(sent) == 1 and body["model"] == "new":
            return httpx.Response(400, json={"error": {"message": "Unsupported parameter: 'max_tokens' is not "
                                                       "supported with this model. Use 'max_completion_tokens' instead."}})
        if body["model"] == "reasoning" and body.get("max_completion_tokens", 0) < 4000:
            return httpx.Response(200, json={"choices": [{"message": {"content": ""}, "finish_reason": "length"}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}]})

    t = httpx.MockTransport(handler)
    key = "sk-test-secret-123456"
    assert ai.chat(ai.AIConfig("openai", "https://x/v1", "gpt", key), "s", "u", transport=t) == "OK"
    assert "max_completion_tokens" in sent[-1] and "max_tokens" not in sent[-1]
    sent.clear()
    assert ai.chat(ai.AIConfig("deepseek", "https://x", "new", key), "s", "u", transport=t) == "OK"
    assert "max_tokens" in sent[0] and "max_completion_tokens" in sent[1]
    sent.clear()
    assert ai.chat(ai.AIConfig("openai", "https://x/v1", "reasoning", key), "s", "u", max_tokens=5, transport=t) == "OK"
    assert sent[0]["max_completion_tokens"] == 5 and sent[1]["max_completion_tokens"] == 4000


def test_ai_provider_key_encrypted_masked_and_redacted(admin, db):
    r = admin.post("/api/v1/ai/providers", json={"kind": "openai", "name": "OpenAI", "model": "gpt-test",
                                                 "api_key": "sk-test-secret-123456"})
    assert r.status_code == 201
    body = r.json()
    assert body["api_key_masked"] == "sk-...3456" and "sk-test-secret-123456" not in r.text
    row = db.query(AIProvider).one()
    assert "sk-test" not in row.api_key_enc and decrypt_secret(row.api_key_enc) == "sk-test-secret-123456"
    assert "sk-test-secret" not in admin.get("/api/v1/ai/providers").text
    assert "sk-test-secret" not in json.dumps([a.details for a in db.query(AuditLog).all()])
    assert "[REDACTED]" in redact("key sk-test-secret-123456 used")
    rec = logging.LogRecord("x", logging.INFO, "", 0, "auth Bearer abc.def.ghi password=hunter2", None, None)
    out = JsonFormatter().format(rec)
    assert "abc.def" not in out and "hunter2" not in out


def test_ai_insight_without_provider(admin):
    pf, *_ = _setup_portfolio(admin)
    r = admin.post("/api/v1/ai/insights", json={"portfolio_id": pf["id"], "task": "risk"})
    assert r.status_code == 409


def test_ai_facts_are_backend_numbers():
    summary = {"portfolio": {"id": 1, "name": "P", "base_currency": "USD"}, "totals": {"market_value": "10"},
               "holdings": [{"ticker": "A", "currency": "USD", "sector": "T", "quantity": "1", "price": "10",
                             "market_value_base": "10", "unrealized_pct": "0", "day_change_pct": "1",
                             "allocation_pct": "100", "stale": False, "avg_cost": "x"}],
               "exposure": {}, "best": None, "worst": None, "freshness": {}, "warnings": []}
    facts = ai.build_facts(summary, [])
    assert "avg_cost" not in facts["holdings"][0] and facts["totals"]["market_value"] == "10"


# ----------------------------------------------------------------------------- simulator

def test_simulator_defaults_persist_and_validation(admin):
    r = admin.get("/api/v1/simulator/config").json()
    assert r["config"]["rotation_enabled"] is True and r["config"]["page_duration_s"] == 10
    assert r["refresh"]["requested_s"] == 10 and r["refresh"]["effective_s"] == 60 and r["refresh"]["clamped"]
    cfg = {**r["config"], "page_duration_s": 0, "api_key": "lsk_abcdef12_secretsecret", "selected_page": 2}
    p = admin.put("/api/v1/simulator/config", json={"config": cfg}).json()
    assert p["config"]["page_duration_s"] == 1 and "page_duration_s" in p["warnings"]
    assert p["config"]["api_key_set"] is True and "api_key" not in p["config"]
    assert admin.put("/api/v1/simulator/runtime", json={"selected_page": 3, "rotation_enabled": False}).status_code == 200
    again = admin.get("/api/v1/simulator/config").json()
    assert again["config"]["selected_page"] == 3 and again["config"]["rotation_enabled"] is False
    events = admin.get("/api/v1/simulator/events").json()
    assert any(e["kind"] == "validation_warning" for e in events)
    assert "secretsecret" not in json.dumps(events)


def test_simulator_reset_requires_confirmation(admin):
    assert admin.post("/api/v1/simulator/reset", json={}).status_code == 400
    assert admin.post("/api/v1/simulator/reset", json={"confirm": True}).status_code == 200


def test_simulator_fixture_and_live_match_device_contract(admin):
    fx = admin.get("/api/v1/simulator/fixture").json()
    assert [p["k"] for p in fx["pages"]] == ["summary", "holdings", "benchmarks"]
    pf, *_ = _setup_portfolio(admin)
    live = admin.get(f"/api/v1/simulator/dashboard?portfolio_id={pf['id']}").json()
    assert set(live) == set(fx) - set() and live["v"] == 1
    chk = admin.get("/api/v1/simulator/refresh-check?profile=UNKNOWN&requested=10").json()
    assert chk["effective_s"] == 180 and chk["fallback"]


def test_simulator_disabled_in_production(admin, monkeypatch):
    from app.core import config
    monkeypatch.setattr(config.get_settings(), "simulator_enabled", False)
    assert admin.get("/api/v1/simulator/config").status_code == 404


def test_demo_seed_and_remove(admin):
    r = admin.post("/api/v1/demo/seed").json()
    assert r["created"]
    assert admin.post("/api/v1/demo/remove", json={}).status_code == 400
    assert admin.post("/api/v1/demo/remove", json={"confirm": True}).json()["portfolios"] == 1
