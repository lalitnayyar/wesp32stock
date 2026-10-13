"""Telegram bot settings, status, test and 'send to Telegram' endpoints (admin only)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.crypto import mask_secret
from ..core.db import get_db
from ..core.security import current_admin
from ..models import Portfolio, User
from ..services import telegram as tg
from ..services.audit import audit

router = APIRouter(prefix="/api/v1/telegram", tags=["telegram"])


class ConfigIn(BaseModel):
    enabled: bool | None = None
    bot_token: str | None = Field(None, max_length=200, pattern=r"^\d{6,12}:[A-Za-z0-9_\-]{30,}$",
                                  description="Write-only; never returned")
    clear_token: bool = False
    allowed_chat_ids: list[int] | None = Field(None, max_length=20)
    default_portfolio_id: int | None = None


class SendIn(BaseModel):
    text: str = Field(min_length=1, max_length=20000)


def cfg_out(db: Session) -> dict:
    cfg = tg.load_config(db)
    return {"enabled": cfg["enabled"], "has_token": bool(cfg["token_enc"]),
            "token_masked": mask_secret(tg.token_of(cfg)), "allowed_chat_ids": cfg["allowed_chat_ids"],
            "default_portfolio_id": cfg["default_portfolio_id"], "status": tg.status(),
            "commands": [{"command": c, "description": d} for c, d in tg.COMMANDS],
            "configured": bool(cfg["token_enc"] and cfg["allowed_chat_ids"])}


@router.get("/config")
def get_config(db: Session = Depends(get_db), _: User = Depends(current_admin)):
    return cfg_out(db)


@router.put("/config")
def put_config(body: ConfigIn, db: Session = Depends(get_db), user: User = Depends(current_admin)):
    cfg = tg.load_config(db)
    if body.default_portfolio_id is not None and db.get(Portfolio, body.default_portfolio_id) is None:
        raise HTTPException(422, "Default portfolio not found")
    if body.enabled is not None:
        cfg["enabled"] = body.enabled
    if body.allowed_chat_ids is not None:
        cfg["allowed_chat_ids"] = sorted(set(body.allowed_chat_ids))
    if "default_portfolio_id" in body.model_fields_set:
        cfg["default_portfolio_id"] = body.default_portfolio_id
    if body.clear_token:
        tg.set_token(cfg, None)
    elif body.bot_token:
        tg.set_token(cfg, body.bot_token)
    if cfg["enabled"] and not cfg["token_enc"]:
        raise HTTPException(422, "A bot token is required to enable the bot")
    tg.save_config(db, cfg)
    audit(db, user.username, "telegram_updated", "telegram", "",
          {**body.model_dump(include={"enabled", "allowed_chat_ids", "default_portfolio_id"}, exclude_none=True),
           "credential": "cleared" if body.clear_token else "changed" if body.bot_token else "unchanged"})
    return cfg_out(db)


@router.post("/test")
def test(db: Session = Depends(get_db), user: User = Depends(current_admin)):
    """Check the token with getMe, register the slash commands and greet every allowed chat."""
    cfg = tg.load_config(db)
    token = tg.token_of(cfg)
    if not token:
        raise HTTPException(409, "No bot token configured")
    try:
        info = tg.bot_info(token)
        sent = tg.send_to_allowed(db, f"✅ Lalit Stock bot @{info['username']} is connected. Send /help.") \
            if cfg["allowed_chat_ids"] else None
    except tg.TelegramError as exc:
        raise HTTPException(502, str(exc))
    audit(db, user.username, "telegram_tested", "telegram", "", {"bot": info["username"]})
    return {"ok": True, "bot": info, "sent": sent,
            "message": f"Bot @{info['username']} OK" + ("" if sent else "; add a chat ID to receive messages")}


@router.post("/send")
def send(body: SendIn, db: Session = Depends(get_db), user: User = Depends(current_admin)):
    try:
        out = tg.send_to_allowed(db, body.text)
    except tg.TelegramError as exc:
        raise HTTPException(409 if "configured" in str(exc) else 502, str(exc))
    audit(db, user.username, "telegram_sent", "telegram", "", {"chats": out["chats"], "chars": len(body.text)})
    return out
