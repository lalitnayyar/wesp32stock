"""Docker E-Paper simulator support API (development/QA only).

Disabled in production unless SIMULATOR_ENABLED=true. All endpoints require an admin session.
Simulator state is stored in its own tables and never touches real device configuration.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.db import get_db
from ..core.logging import redact
from ..core.security import current_admin
from ..models import Portfolio, SimulatorEvent, SimulatorState, User
from ..services import device_rules
from ..services.audit import audit
from .common import dashboard_for, get_or_404

router = APIRouter(prefix="/api/v1/simulator", tags=["simulator"])

SIM_ID = "default"
# Simulator-only keys stored next to the shared device config (never sent to hardware).
SIM_DEFAULTS = {
    "device_id": "SIM-001",
    "device_name": "Simulated E-Paper",
    "wifi_ssid": "Simulated-WiFi",
    "api_url": "fixture://shared/fixtures/dashboard_3page.json",
    "api_key_set": False,
    "mode": "fixture",          # fixture | live
    "portfolio_id": None,
}


def require_simulator(_: User = Depends(current_admin)) -> User:
    if not get_settings().simulator_active:
        raise HTTPException(404, "Simulator is disabled in this deployment")
    return _


def _state(db: Session) -> SimulatorState:
    st = db.get(SimulatorState, SIM_ID)
    if st is None:
        st = SimulatorState(id=SIM_ID, config={**device_rules.default_config(), **SIM_DEFAULTS}, runtime={})
        db.add(st)
        db.commit()
    return st


def _event(db: Session, kind: str, message: str) -> None:
    db.add(SimulatorEvent(kind=kind[:32], message=redact(message)[:500]))
    db.commit()


@router.get("/contract")
def contract(_: User = Depends(require_simulator)):
    return {"device_config": device_rules.load_shared("device_config.json"),
            "panel_profiles": device_rules.panel_profiles(),
            "layout": device_rules.layout(), "layouts": {n: device_rules.layout(n) for n in
                                                          ("layout.json", "layout_400x300.json")}}


@router.get("/config")
def get_config(db: Session = Depends(get_db), _: User = Depends(require_simulator)):
    st = _state(db)
    refresh = device_rules.compute_refresh(st.config.get("panel_profile", "UNKNOWN"), st.config.get("page_duration_s", 10))
    return {"config": st.config, "runtime": st.runtime, "refresh": refresh.as_dict(), "updated_at": st.updated_at}


class SimConfigIn(BaseModel):
    config: dict[str, Any]
    runtime: dict[str, Any] | None = None


@router.put("/config")
def put_config(body: SimConfigIn, db: Session = Depends(get_db), user: User = Depends(require_simulator)):
    st = _state(db)
    shared, warnings = device_rules.validate_config(body.config)
    sim = {k: body.config.get(k, st.config.get(k, v)) for k, v in SIM_DEFAULTS.items()}
    # never persist a plaintext key; the simulator only records whether one was entered
    if "api_key" in body.config:
        sim["api_key_set"] = bool(body.config.get("api_key"))
    if sim["mode"] not in ("fixture", "live"):
        warnings["mode"] = "mode must be fixture or live; using fixture"
        sim["mode"] = "fixture"
    if sim["portfolio_id"] is not None:
        try:
            sim["portfolio_id"] = int(sim["portfolio_id"])
            get_or_404(db, Portfolio, sim["portfolio_id"], "Portfolio")
        except (TypeError, ValueError):
            sim["portfolio_id"] = None
    for k in ("device_id", "device_name", "wifi_ssid", "api_url"):
        sim[k] = str(sim[k])[:100]
    st.config = {**shared, **sim}
    if body.runtime is not None:
        raw = json.dumps(body.runtime)
        if len(raw) > 8192:
            raise HTTPException(413, "runtime state too large")
        st.runtime = json.loads(redact(raw))
    db.commit()
    refresh = device_rules.compute_refresh(st.config["panel_profile"], st.config["page_duration_s"])
    _event(db, "config_saved", f"requested={refresh.requested_s}s effective={refresh.effective_s}s "
                               f"profile={refresh.profile} warnings={list(warnings)}")
    if refresh.clamped:
        _event(db, "validation_warning", refresh.reason)
    audit(db, user.username, "simulator_config_saved", "simulator", SIM_ID)
    return {"config": st.config, "runtime": st.runtime, "warnings": warnings, "refresh": refresh.as_dict()}


@router.put("/runtime")
def put_runtime(body: dict[str, Any], db: Session = Depends(get_db), _: User = Depends(require_simulator)):
    """Persist volatile simulator state (selected page, paused, counters) - mirrors ESP32 NVS writes."""
    raw = json.dumps(body)
    if len(raw) > 8192:
        raise HTTPException(413, "runtime state too large")
    st = _state(db)
    st.runtime = json.loads(redact(raw))
    # The selected page and rotation flag are part of the persisted device config, as on the ESP32.
    for key in ("selected_page", "rotation_enabled"):
        if key in body:
            val, ok = device_rules.validate_field(key, body[key])
            if ok:
                st.config = {**st.config, key: val}
    db.commit()
    return {"ok": True}


@router.post("/reset")
def reset(body: dict, db: Session = Depends(get_db), user: User = Depends(require_simulator)):
    if body.get("confirm") is not True:
        raise HTTPException(400, "Confirmation required: send {\"confirm\": true}")
    st = _state(db)
    st.config = {**device_rules.default_config(), **SIM_DEFAULTS}
    st.runtime = {}
    db.query(SimulatorEvent).delete()
    db.commit()
    _event(db, "reset", "Simulator state cleared")
    audit(db, user.username, "simulator_reset", "simulator", SIM_ID)
    return {"ok": True, "config": st.config}


@router.get("/refresh-check")
def refresh_check(profile: str, requested: int, _: User = Depends(require_simulator)):
    val, ok = device_rules.validate_field("page_duration_s", requested)
    res = device_rules.compute_refresh(profile, val).as_dict()
    res["input_valid"] = ok
    return res


@router.get("/fixture")
def fixture(panel: str | None = Query(None, max_length=40), _: User = Depends(require_simulator)):
    """The generated shared fixture for the panel's build (same file the firmware host tests use)."""
    spec = device_rules.panel_spec(panel)
    build = device_rules.panel_profiles()["profiles"][spec["profile"]].get("build")
    name = "dashboard_3page.json" if spec["layout"]["id"] == "168x384" else f"dashboard_3page_{build}.json"
    path = get_settings().shared_dir / "fixtures" / name
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/dashboard")
def live_dashboard(portfolio_id: int | None = None, rows: int = 8, summary: bool = True, bench: bool = True,
                   panel: str | None = Query(None, max_length=40), db: Session = Depends(get_db),
                   _: User = Depends(require_simulator)):
    """Live mode: the exact payload /api/v1/device/dashboard would return, authorised by the admin
    session instead of a real device key (no real API key needed)."""
    st = _state(db)
    pf = db.get(Portfolio, portfolio_id) if portfolio_id else None
    display = {"rows_per_page": max(4, min(8, rows)), "show_summary_page": summary, "show_benchmarks_page": bench}
    return dashboard_for(db, portfolio=pf, display=display, device_uid=st.config.get("device_id", "SIM-001"),
                         device_name=st.config.get("device_name", "Simulated E-Paper"),
                         panel_profile=panel or st.config.get("panel_profile"))


class EventIn(BaseModel):
    kind: str = Field(min_length=1, max_length=32)
    message: str = Field("", max_length=500)


@router.post("/events")
def add_event(body: EventIn, db: Session = Depends(get_db), _: User = Depends(require_simulator)):
    _event(db, body.kind, body.message)
    return {"ok": True}


@router.get("/events")
def events(limit: int = 100, db: Session = Depends(get_db), _: User = Depends(require_simulator)):
    rows = db.query(SimulatorEvent).order_by(SimulatorEvent.id.desc()).limit(min(limit, 500)).all()
    return [{"id": r.id, "ts": r.ts, "kind": r.kind, "message": r.message} for r in rows]
