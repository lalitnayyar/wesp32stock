"""Health, about, settings, market status and audit endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from .. import __version__
from ..core.config import get_settings
from ..core.db import get_db
from ..core.security import current_admin
from ..models import AuditLog, Quote, Stock, User
from ..services import scheduler, seed, settings_store
from ..services.audit import audit
from ..services.market import service as market
from .common import DISCLAIMER, OWNER

router = APIRouter(tags=["system"])


@router.get("/api/health")
def health():
    return {"status": "ok", "version": __version__}


@router.get("/api/health/ready")
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(503, f"database unavailable: {type(exc).__name__}")
    return {"status": "ready", "scheduler": scheduler.status()["running"], "provider": get_settings().market_provider}


@router.get("/api/v1/about")
def about():
    s = get_settings()
    return {"application": "Lalit Stock Application", "version": __version__, "owner": OWNER,
            "disclaimer": DISCLAIMER, "environment": s.app_env, "simulator_enabled": s.simulator_active,
            "market_provider": s.market_provider}


@router.get("/api/v1/settings")
def get_settings_(db: Session = Depends(get_db), _: User = Depends(current_admin)):
    return {"values": settings_store.get_all(db), "schema": settings_store.describe()}


@router.put("/api/v1/settings")
def put_settings(body: dict[str, Any], db: Session = Depends(get_db), user: User = Depends(current_admin)):
    body.pop("demo_data_loaded", None)
    try:
        clean = settings_store.set_many(db, body)
    except settings_store.SettingError as exc:
        raise HTTPException(422, str(exc))
    if "quote_refresh_s" in clean:
        scheduler.reschedule_quotes(clean["quote_refresh_s"])
    audit(db, user.username, "settings_updated", "settings", "", clean)
    return {"values": settings_store.get_all(db)}


@router.get("/api/v1/market/status")
def market_status(db: Session = Depends(get_db), _: User = Depends(current_admin)):
    lp = market.LAST_POLL
    stale_after = settings_store.get(db, "stale_after_s")
    quotes = db.query(Stock, Quote).outerjoin(Quote, Quote.stock_id == Stock.id).filter(Stock.active.is_(True)).all()
    return {
        "provider": get_settings().market_provider,
        "quote_refresh_s": settings_store.get(db, "quote_refresh_s"),
        "scheduler": scheduler.status(),
        "last_poll": {"started_at": lp.started_at, "finished_at": lp.finished_at,
                      "last_success_at": lp.last_success_at, "symbols": lp.symbols, "ok": lp.ok,
                      "failed": lp.failed, "skipped": lp.skipped, "errors": lp.errors},
        "symbols": [{"ticker": s.ticker, "data_quality": s.data_quality,
                     "last_poll_at": q.last_poll_at if q else None,
                     "last_success_at": q.last_success_at if q else None,
                     "quote_time": q.quote_time if q else None,
                     "market_state": q.market_state if q else "UNKNOWN",
                     "stale": market.is_stale(q, stale_after),
                     "last_error": q.last_error if q else None} for s, q in quotes],
    }


@router.post("/api/v1/market/refresh")
def market_refresh(db: Session = Depends(get_db), user: User = Depends(current_admin)):
    stats = market.poll_once(db, wait_s=120)
    audit(db, user.username, "market_refresh", "market")
    return {"ok": stats.ok, "failed": stats.failed, "skipped": stats.skipped, "errors": stats.errors}


@router.post("/api/v1/market/history")
def market_history(db: Session = Depends(get_db), user: User = Depends(current_admin)):
    out = market.refresh_history(db)
    audit(db, user.username, "history_refresh", "market")
    return out


@router.get("/api/v1/audit")
def audit_log(limit: int = 200, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    rows = db.query(AuditLog).order_by(AuditLog.ts.desc()).limit(min(limit, 1000)).all()
    return [{"id": r.id, "ts": r.ts, "actor": r.actor, "action": r.action, "entity": r.entity,
             "entity_id": r.entity_id, "details": r.details} for r in rows]


@router.post("/api/v1/demo/seed")
def demo_seed(db: Session = Depends(get_db), user: User = Depends(current_admin)):
    out = seed.seed_demo(db)
    audit(db, user.username, "demo_seeded", "demo")
    return out


@router.post("/api/v1/demo/remove")
def demo_remove(body: dict, db: Session = Depends(get_db), user: User = Depends(current_admin)):
    if body.get("confirm") is not True:
        raise HTTPException(400, "Confirmation required: send {\"confirm\": true}")
    out = seed.remove_demo(db)
    audit(db, user.username, "demo_removed", "demo", "", out)
    return out
