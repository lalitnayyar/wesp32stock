"""Telegram bot: talk to your portfolios with slash commands and receive AI insights.

The bot uses long polling (getUpdates), so the server needs only outbound HTTPS to api.telegram.org;
no public domain, webhook or port forwarding is required. Only chats on the allow-list are answered.
The bot token is encrypted at rest and never returned or logged in full. Not financial advice.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from ..core.crypto import decrypt_secret, encrypt_secret
from ..core.db import SessionLocal
from ..models import AppSetting, Portfolio
from . import analytics
from .ai import providers as ai
from .ai import run as ai_run
from .audit import audit

log = logging.getLogger(__name__)
# httpx logs request URLs at INFO and Telegram puts the token in the URL path.
logging.getLogger("httpx").setLevel(logging.WARNING)

# Override for a self-hosted Bot API server (https://github.com/tdlib/telegram-bot-api).
API = os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org").rstrip("/")
MAX_MSG = 4000  # Telegram's hard limit is 4096 characters per message
CFG_KEY, OFFSET_KEY, CHATS_KEY = "telegram", "telegram_offset", "telegram_chats"
DEFAULTS = {"enabled": False, "token_enc": None, "allowed_chat_ids": [], "default_portfolio_id": None}
FOOTER = "Not financial advice. Data may be delayed."

COMMANDS = [
    ("help", "List commands"),
    ("id", "Show this chat's ID"),
    ("portfolios", "List portfolios"),
    ("use", "Select a portfolio: /use <number>"),
    ("summary", "Value, P/L and day change"),
    ("holdings", "Holdings with price and P/L"),
    ("movers", "Best and worst performers today"),
    ("exposure", "Sector and currency exposure"),
    ("benchmarks", "Benchmark index returns"),
    ("insight", "AI insight: /insight [task]"),
    ("ask", "Ask the AI: /ask <question>"),
]
TASK_ALIASES = {"summary": "portfolio_summary", "daily": "daily_summary", "contributors": "contributors",
                "concentration": "concentration", "unusual": "unusual_moves", "benchmarks": "benchmark_comparison",
                "risk": "risk"}


TRANSPORT: httpx.BaseTransport | None = None  # tests inject a mock transport here


class TelegramError(Exception):
    pass


# ----------------------------------------------------------------------------- config

def _get(db: Session, key: str, default):
    row = db.get(AppSetting, key)
    return default if row is None else row.value


def _put(db: Session, key: str, value) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value
    db.commit()


def load_config(db: Session) -> dict:
    return {**DEFAULTS, **(_get(db, CFG_KEY, {}) or {})}


def save_config(db: Session, cfg: dict) -> None:
    _put(db, CFG_KEY, {k: cfg.get(k, DEFAULTS[k]) for k in DEFAULTS})
    WAKE.set()


def token_of(cfg: dict) -> str | None:
    return decrypt_secret(cfg.get("token_enc"))


def set_token(cfg: dict, token: str | None) -> None:
    cfg["token_enc"] = encrypt_secret(token) if token else None


# ----------------------------------------------------------------------------- Bot API

class Bot:
    def __init__(self, token: str, transport: httpx.BaseTransport | None = None, timeout: float = 40):
        self._c = httpx.Client(base_url=f"{API}/bot{token}", timeout=timeout,
                                transport=transport or TRANSPORT)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._c.close()

    def call(self, method: str, **params):
        try:
            r = self._c.post(f"/{method}", json=params)
        except httpx.HTTPError as exc:
            raise TelegramError(f"Telegram unreachable: {type(exc).__name__}") from None
        try:
            body = r.json()
        except ValueError:
            raise TelegramError(f"HTTP {r.status_code} from Telegram") from None
        if not body.get("ok"):
            raise TelegramError(f"{method}: {body.get('description') or r.status_code}")
        return body.get("result")

    def send(self, chat_id: int, text: str) -> int:
        """Send plain text (AI output is free-form, so no parse_mode to break on), split to fit."""
        parts = split_text(text)
        for p in parts:
            self.call("sendMessage", chat_id=chat_id, text=p, disable_web_page_preview=True)
        return len(parts)


def split_text(text: str, limit: int = MAX_MSG) -> list[str]:
    text = text.strip() or "(empty)"
    parts = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        parts.append(text[:cut].rstrip())
        text = text[cut:].lstrip("\n")
    parts.append(text)
    return parts


# ----------------------------------------------------------------------------- formatting

def _n(v, signed: bool = False, unit: str = "") -> str:
    if v is None:
        return "—"
    x = float(v)
    return (f"{x:+,.2f}" if signed else f"{x:,.2f}") + unit


def fmt_summary(s: dict) -> str:
    t, f = s["totals"], s["freshness"]
    ccy = s["portfolio"]["base_currency"]
    lines = [f"📊 {s['portfolio']['name']} ({ccy})",
             f"Value: {_n(t['market_value'])}",
             f"Invested: {_n(t['invested'])}",
             f"Unrealized: {_n(t['unrealized_pl'], True)} ({_n(t['unrealized_pct'], True, '%')})",
             f"Today: {_n(t['day_pl'], True)} ({_n(t['day_pct'], True, '%')})",
             f"Realized: {_n(t['realized_pl'], True)} · Dividends: {_n(t['dividends'])}",
             f"Cash: {_n(t['cash'])} · Holdings: {t['active_holdings']}"]
    if s["best"]:
        lines.append(f"Best: {s['best']['ticker']} {_n(s['best']['day_change_pct'], True, '%')} · "
                     f"Worst: {s['worst']['ticker']} {_n(s['worst']['day_change_pct'], True, '%')}")
    if f["stale_count"]:
        lines.append(f"⚠ {f['stale_count']}/{f['total']} quotes stale")
    lines += [f"⚠ {w}" for w in s["warnings"][:3]]
    return "\n".join(lines)


def fmt_holdings(s: dict) -> str:
    if not s["holdings"]:
        return "No holdings."
    lines = [f"📋 {s['portfolio']['name']} holdings"]
    for h in sorted(s["holdings"], key=lambda h: -float(h["allocation_pct"] or 0)):
        lines.append(f"{h['ticker']}: {h['quantity']} @ {_n(h['price'])} {h['currency']} · "
                     f"day {_n(h['day_change_pct'], True, '%')} · P/L {_n(h['unrealized_pct'], True, '%')} · "
                     f"{_n(h['allocation_pct'], unit='%')}" + (" (stale)" if h["stale"] else ""))
    return "\n".join(lines)


def fmt_movers(s: dict, n: int = 3) -> str:
    rows = [h for h in s["holdings"] if h["day_change_pct"] is not None]
    if not rows:
        return "No price changes available yet."
    rows.sort(key=lambda h: float(h["day_change_pct"]))
    up = [f"  {h['ticker']} {_n(h['day_change_pct'], True, '%')} ({_n(h['day_pl'], True)} {h['currency']})"
          for h in reversed(rows[-n:])]
    down = [f"  {h['ticker']} {_n(h['day_change_pct'], True, '%')} ({_n(h['day_pl'], True)} {h['currency']})"
            for h in rows[:n]]
    return "\n".join([f"🚀 Top movers · {s['portfolio']['name']}", "Up:", *up, "Down:", *down])


def fmt_exposure(s: dict) -> str:
    lines = [f"🧭 Exposure · {s['portfolio']['name']}", "Sector:"]
    lines += [f"  {k}: {_n(v, unit='%')}" for k, v in s["exposure"]["sector"].items()]
    lines.append("Currency:")
    lines += [f"  {k}: {_n(v, unit='%')}" for k, v in s["exposure"]["currency"].items()]
    return "\n".join(lines)


def fmt_benchmarks(rows: list[dict]) -> str:
    if not rows:
        return "No benchmarks configured."
    lines = ["🌐 Benchmarks (day · 1M · YTD · 1Y)"]
    for b in rows:
        lines.append(f"{b['name']}: {_n(b['level'])} · {_n(b['day_change_pct'], True, '%')} · "
                     f"{_n(b.get('ret_1m'), True, '%')} · {_n(b.get('ret_ytd'), True, '%')} · "
                     f"{_n(b.get('ret_1y'), True, '%')}" + (" (stale)" if b["stale"] else ""))
    return "\n".join(lines)


def help_text() -> str:
    tasks = ", ".join(TASK_ALIASES)
    return "\n".join(["🤖 Lalit Stock Application bot", *[f"/{c} - {d}" for c, d in COMMANDS],
                      f"Insight tasks: {tasks}", "", FOOTER])


# ----------------------------------------------------------------------------- commands

def _portfolios(db: Session) -> list[Portfolio]:
    return db.query(Portfolio).order_by(Portfolio.id).all()


def _selected(db: Session, cfg: dict, chat_id: int) -> Portfolio | None:
    pid = (_get(db, CHATS_KEY, {}) or {}).get(str(chat_id)) or cfg.get("default_portfolio_id")
    pf = db.get(Portfolio, pid) if pid else None
    if pf is None:
        pfs = _portfolios(db)
        pf = pfs[0] if pfs else None
    return pf


def handle_command(db: Session, cfg: dict, chat_id: int, text: str, ai_transport=None) -> str:
    """Return the reply for one message from an authorised chat."""
    cmd, _, arg = text.strip().partition(" ")
    cmd = cmd.split("@")[0].lstrip("/").lower()  # "/summary@MyBot" in group chats
    arg = arg.strip()
    if cmd in ("start", "help"):
        return help_text()
    if cmd == "id":
        return f"This chat's ID is {chat_id}."
    if cmd == "portfolios":
        pfs = _portfolios(db)
        cur = _selected(db, cfg, chat_id)
        if not pfs:
            return "No portfolios yet. Create one in the web admin."
        return "\n".join(["Portfolios (select with /use <number>):",
                          *[f"{i}. {p.name} ({p.base_currency})" + (" ✓" if cur and p.id == cur.id else "")
                            for i, p in enumerate(pfs, 1)]])
    if cmd == "use":
        pfs = _portfolios(db)
        match = None
        if arg.isdigit() and 1 <= int(arg) <= len(pfs):
            match = pfs[int(arg) - 1]
        else:
            match = next((p for p in pfs if arg and p.name.lower() == arg.lower()), None)
        if match is None:
            return "Usage: /use <number from /portfolios>"
        chats = dict(_get(db, CHATS_KEY, {}) or {})
        chats[str(chat_id)] = match.id
        _put(db, CHATS_KEY, chats)
        return f"Selected portfolio: {match.name}"
    if cmd == "benchmarks":
        return fmt_benchmarks(analytics.benchmarks(db))
    if cmd not in ("summary", "holdings", "movers", "exposure", "insight", "ask"):
        return f"Unknown command /{cmd}. Send /help for the list."
    pf = _selected(db, cfg, chat_id)
    if pf is None:
        return "No portfolios yet. Create one in the web admin."
    if cmd in ("summary", "holdings", "movers", "exposure"):
        s = analytics.portfolio_summary(db, pf)
        return {"summary": fmt_summary, "holdings": fmt_holdings, "movers": fmt_movers, "exposure": fmt_exposure}[cmd](s)
    if cmd == "ask" and not arg:
        return "Usage: /ask <question about your portfolio>"
    task = "question" if cmd == "ask" else TASK_ALIASES.get(arg.lower() or "summary", arg.lower())
    if task not in ai.TASKS:
        return f"Unknown insight task '{arg}'. Choose one of: {', '.join(TASK_ALIASES)}"
    try:
        out = ai_run.generate(db, pf, task, arg if cmd == "ask" else None, transport=ai_transport)
    except ai_run.NoProvider:
        return "No AI provider is configured. Add one under AI Settings in the web admin."
    except ai.AIError as exc:
        return f"AI provider error: {exc}"
    except Exception as exc:
        return f"AI provider unreachable: {type(exc).__name__}"
    audit(db, "telegram", "ai_insight", "portfolio", pf.id, {"task": task, "provider": out["provider"], "chat": chat_id})
    return f"🧠 {pf.name} · {out['provider']} ({out['model']})\n\n{out['text']}\n\n{out['disclaimer']}"


def handle_update(db: Session, cfg: dict, bot: Bot, update: dict, ai_transport=None) -> None:
    msg = update.get("message") or update.get("edited_message")
    if not msg or not isinstance(msg.get("text"), str) or not msg["text"].startswith("/"):
        return
    chat_id = msg["chat"]["id"]
    if chat_id not in cfg["allowed_chat_ids"]:
        # Unknown chats learn only their own ID, so the owner can allow it in the web admin.
        audit(db, "telegram", "telegram_denied", "chat", chat_id, {"from": (msg.get("from") or {}).get("username")})
        bot.send(chat_id, f"This chat is not authorised. Chat ID: {chat_id}\n"
                          "Add it under Settings → Telegram bot in the Lalit Stock web admin.")
        return
    if msg["text"].split()[0].split("@")[0].lower() in ("/ask", "/insight"):
        bot.call("sendChatAction", chat_id=chat_id, action="typing")
    bot.send(chat_id, handle_command(db, cfg, chat_id, msg["text"], ai_transport))


def send_to_allowed(db: Session, text: str, transport=None) -> dict:
    """Send text to every allowed chat. Used by the web admin (AI insight 'Send to Telegram', test)."""
    cfg = load_config(db)
    token = token_of(cfg)
    if not token:
        raise TelegramError("No bot token configured")
    if not cfg["allowed_chat_ids"]:
        raise TelegramError("No allowed chat IDs configured")
    sent, errors = 0, []
    with Bot(token, transport) as bot:
        for cid in cfg["allowed_chat_ids"]:
            try:
                sent += bot.send(cid, text)
            except TelegramError as exc:
                errors.append(f"{cid}: {exc}")
    if errors and not sent:
        raise TelegramError("; ".join(errors))
    return {"chats": len(cfg["allowed_chat_ids"]) - len(errors), "messages": sent, "errors": errors}


def bot_info(token: str, transport=None) -> dict:
    with Bot(token, transport, timeout=15) as bot:
        me = bot.call("getMe")
        bot.call("setMyCommands", commands=[{"command": c, "description": d} for c, d in COMMANDS])
    return {"username": me.get("username"), "name": me.get("first_name")}


# ----------------------------------------------------------------------------- poller

STATUS: dict = {"running": False, "polling": False, "last_poll_at": None, "last_error": None, "bot_username": None,
                "messages_handled": 0}
WAKE = threading.Event()
_stop = threading.Event()
_thread: threading.Thread | None = None


def poll_once(db: Session, cfg: dict, token: str, transport=None, timeout_s: int = 25) -> int:
    offset = _get(db, OFFSET_KEY, 0) or 0
    with Bot(token, transport, timeout=timeout_s + 15) as bot:
        updates = bot.call("getUpdates", offset=offset, timeout=timeout_s, allowed_updates=["message"])
        for u in updates:
            # Advance the offset first so a message that crashes the handler is not retried forever.
            _put(db, OFFSET_KEY, u["update_id"] + 1)
            try:
                handle_update(db, cfg, bot, u)
                STATUS["messages_handled"] += 1
            except Exception:
                db.rollback()
                log.exception("telegram update %s failed", u.get("update_id"))
    return len(updates)


def _loop() -> None:
    backoff = 5
    known_token = None
    while not _stop.is_set():
        db = SessionLocal()
        try:
            cfg = load_config(db)
            token = token_of(cfg)
            if not (cfg["enabled"] and token):
                STATUS.update(polling=False, last_error=None)
                db.close()
                WAKE.wait(60)
                WAKE.clear()
                continue
            if token != known_token:
                STATUS["bot_username"] = bot_info(token)["username"]
                known_token = token
            STATUS["polling"] = True
            poll_once(db, cfg, token)
            STATUS.update(last_poll_at=datetime.now(timezone.utc).isoformat(), last_error=None)
            backoff = 5
        except Exception as exc:
            STATUS.update(polling=False, last_error=str(exc)[:300])
            log.warning("telegram poll failed: %s", exc)
            _stop.wait(backoff)
            backoff = min(backoff * 2, 300)
        finally:
            db.close()


def start() -> None:
    global _thread
    if _thread is not None:
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="telegram-bot", daemon=True)
    _thread.start()
    STATUS["running"] = True


def shutdown() -> None:
    global _thread
    _stop.set()
    WAKE.set()
    _thread = None
    STATUS.update(running=False, polling=False)


def status() -> dict:
    return dict(STATUS)
