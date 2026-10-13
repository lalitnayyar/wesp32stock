import json
import logging

import httpx
import pytest

from app.core.logging import JsonFormatter
from app.models import AIProvider, AppSetting
from app.services import telegram as tg
from tests.test_api import _setup_portfolio

TOKEN = "123456789:AAH-test_token_abcdefghijklmnopqrstuvwxyz"


class FakeTelegram:
    """Records Bot API calls; serves queued getUpdates batches."""

    def __init__(self):
        self.calls, self.updates = [], []

    def handler(self, request: httpx.Request):
        assert request.url.path.startswith(f"/bot{TOKEN}/")
        method = request.url.path.rsplit("/", 1)[1]
        body = json.loads(request.content or b"{}")
        self.calls.append((method, body))
        result = {"getMe": {"username": "ls_test_bot", "first_name": "LS"},
                  "getUpdates": self.updates.pop(0) if self.updates else []}.get(method, True)
        return httpx.Response(200, json={"ok": True, "result": result})

    def sent(self):
        return [b for m, b in self.calls if m == "sendMessage"]


@pytest.fixture
def fake(monkeypatch):
    f = FakeTelegram()
    monkeypatch.setattr(tg, "TRANSPORT", httpx.MockTransport(f.handler))
    return f


def _configure(admin, chats=(42,), **extra):
    r = admin.put("/api/v1/telegram/config", json={"bot_token": TOKEN, "enabled": True,
                                                    "allowed_chat_ids": list(chats), **extra})
    assert r.status_code == 200, r.text
    return r.json()


def _msg(uid, chat, text):
    return {"update_id": uid, "message": {"chat": {"id": chat}, "from": {"username": "u"}, "text": text}}


def test_config_token_encrypted_and_masked(admin, db):
    out = _configure(admin)
    assert out["has_token"] and out["token_masked"] == "123...wxyz" and out["configured"]
    assert TOKEN not in admin.get("/api/v1/telegram/config").text
    row = db.get(AppSetting, "telegram")
    assert TOKEN not in json.dumps(row.value)
    assert "telegram" not in admin.get("/api/v1/settings").json()["values"]
    bad = admin.put("/api/v1/telegram/config", json={"bot_token": "not-a-token"})
    assert bad.status_code == 422
    cleared = admin.put("/api/v1/telegram/config", json={"clear_token": True, "enabled": False}).json()
    assert not cleared["has_token"]
    assert admin.put("/api/v1/telegram/config", json={"enabled": True}).status_code == 422


def test_token_redacted_in_logs():
    rec = logging.LogRecord("httpx", logging.INFO, "", 0, f"POST https://api.telegram.org/bot{TOKEN}/getUpdates",
                            None, None)
    assert TOKEN not in JsonFormatter().format(rec)


def test_poll_answers_allowed_chat_and_rejects_others(admin, db, fake):
    _setup_portfolio(admin)
    _configure(admin)
    fake.updates.append([_msg(10, 42, "/summary"), _msg(11, 99, "/holdings"), _msg(12, 42, "hello"),
                         _msg(13, 42, "/holdings@ls_test_bot")])
    cfg = tg.load_config(db)
    assert tg.poll_once(db, cfg, TOKEN, timeout_s=0) == 4
    sent = fake.sent()
    assert sent[0]["chat_id"] == 42 and "Main (USD)" in sent[0]["text"] and "Unrealized" in sent[0]["text"]
    assert sent[1]["chat_id"] == 99 and "not authorised" in sent[1]["text"] and "99" in sent[1]["text"]
    assert "AAPL" not in sent[1]["text"]
    assert sent[2]["chat_id"] == 42 and "AAPL" in sent[2]["text"] and "EMAAR.AE" in sent[2]["text"]
    assert len(sent) == 3  # plain text without a slash is ignored
    assert db.get(AppSetting, "telegram_offset").value == 14
    getupd = [b for m, b in fake.calls if m == "getUpdates"][0]
    assert getupd["offset"] == 0


def test_commands(admin, db):
    _setup_portfolio(admin)
    admin.post("/api/v1/portfolios", json={"name": "Second", "base_currency": "AED"})
    cfg = tg.load_config(db)
    assert "/insight" in tg.handle_command(db, cfg, 1, "/help")
    assert "1. Main (USD) ✓" in tg.handle_command(db, cfg, 1, "/portfolios")
    assert tg.handle_command(db, cfg, 1, "/use 2") == "Selected portfolio: Second"
    assert "Second" in tg.handle_command(db, cfg, 1, "/summary")
    assert "Main" in tg.handle_command(db, cfg, 2, "/summary")  # selection is per chat
    assert "Usage" in tg.handle_command(db, cfg, 1, "/use 9")
    assert "Up:" in tg.handle_command(db, cfg, 2, "/movers")
    assert "Sector:" in tg.handle_command(db, cfg, 2, "/exposure")
    assert "Benchmarks" in tg.handle_command(db, cfg, 2, "/benchmarks") or "No benchmarks" in \
        tg.handle_command(db, cfg, 2, "/benchmarks")
    assert "Unknown command" in tg.handle_command(db, cfg, 2, "/nope")
    assert "No AI provider" in tg.handle_command(db, cfg, 2, "/insight risk")
    assert "Usage" in tg.handle_command(db, cfg, 2, "/ask")
    assert "Unknown insight task" in tg.handle_command(db, cfg, 2, "/insight bogus")


def test_ai_commands_use_default_provider(admin, db):
    _setup_portfolio(admin)
    db.add(AIProvider(kind="openai", name="OAI", base_url="https://x/v1", model="m", api_key_enc=None,
                      enabled=True, is_default=True))
    db.commit()
    from app.core.crypto import encrypt_secret
    p = db.query(AIProvider).one()
    p.api_key_enc = encrypt_secret("sk-test-secret-123456")
    db.commit()
    seen = []

    def ai_handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "Facts: fine"}, "finish_reason": "stop"}]})

    cfg = tg.load_config(db)
    out = tg.handle_command(db, cfg, 1, "/ask Which holding is biggest?", ai_transport=httpx.MockTransport(ai_handler))
    assert "Facts: fine" in out and "not financial advice" in out
    assert "Which holding is biggest?" in seen[0]["messages"][1]["content"]


def test_split_text():
    parts = tg.split_text("line\n" * 2000, limit=100)
    assert all(len(p) <= 100 for p in parts) and "".join(parts).count("line") == 2000


def test_send_and_test_endpoints(admin, fake):
    assert admin.post("/api/v1/telegram/send", json={"text": "hi"}).status_code == 409
    _configure(admin, chats=(42, 43))
    r = admin.post("/api/v1/telegram/test")
    assert r.status_code == 200 and r.json()["bot"]["username"] == "ls_test_bot"
    assert any(m == "setMyCommands" for m, _ in fake.calls)
    long = "# Insight\n" + "x" * 5000
    r = admin.post("/api/v1/telegram/send", json={"text": long})
    assert r.status_code == 200 and r.json() == {"chats": 2, "messages": 4, "errors": []}
