from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..models import Device, Portfolio
from ..services import analytics, settings_store
from ..services.dashboard import build_dashboard

OWNER = {
    "name": "Lalit Nayyar",
    "email": "consult@lalit.cloud",
    "phone": "+971568391973",
}
DISCLAIMER = (
    "This software is informational only and is not financial advice. Market data may be delayed, "
    "incomplete, inaccurate, rate-limited or unavailable. AI output may be wrong. The operator is responsible "
    "for credentials, security, backups, licensing, provider terms and for validating all financial information. "
    "Provided without warranty of fitness, availability or investment performance."
)


def get_or_404(db: Session, model, obj_id, what: str | None = None):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(404, f"{what or model.__name__} not found")
    return obj


def device_online(db: Session, device: Device, now: datetime | None = None) -> bool:
    if device.last_heartbeat_at is None:
        return False
    now = now or datetime.now(timezone.utc)
    return (now - device.last_heartbeat_at).total_seconds() <= settings_store.get(db, "heartbeat_timeout_s")


def dashboard_for(db: Session, *, portfolio: Portfolio | None, display: dict, device_uid: str, device_name: str,
                  panel_profile: str | None = None) -> dict:
    summary = analytics.portfolio_summary(db, portfolio) if portfolio else None
    bench = analytics.benchmarks(db)
    return build_dashboard(summary=summary, bench_rows=bench, display=display, device_uid=device_uid,
                           device_name=device_name, tz=settings_store.get(db, "timezone"),
                           provider=get_settings().market_provider, panel_profile=panel_profile)
