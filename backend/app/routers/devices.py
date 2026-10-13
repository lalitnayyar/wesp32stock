"""Device registry, API-key management, and the authenticated device endpoints."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.security import DEVICE_SCOPES, client_ip, current_admin, generate_api_key, require_device_key
from ..models import ApiAccessLog, ApiKey, Device, Portfolio, User
from ..services import device_rules
from ..services.audit import audit
from ..services.dashboard import DEFAULT_DISPLAY
from .common import dashboard_for, device_online, get_or_404

router = APIRouter(tags=["devices"])

UID_RE = re.compile(r"^[A-Za-z0-9_\-]{3,64}$")


class DisplayConfig(BaseModel):
    rows_per_page: int = Field(8, ge=4, le=8)
    show_summary_page: bool = True
    show_benchmarks_page: bool = True
    page_order: list[str] = ["summary", "holdings", "benchmarks"]
    sort: str = Field("value", pattern="^(value|ticker|change)$")
    # E-Paper module chosen at registration (a real panel profile). The panel the device's firmware reports
    # when it fetches takes precedence, because that is the hardware actually connected.
    panel_profile: str = device_rules.DEFAULT_PROFILE

    @field_validator("panel_profile")
    @classmethod
    def _known_module(cls, v: str) -> str:
        profiles = device_rules.panel_profiles()["profiles"]
        if v not in profiles or not profiles[v].get("build"):
            raise ValueError(f"unknown E-Paper module; choose one of {', '.join(device_rules.modules())}")
        return v


class DeviceIn(BaseModel):
    device_uid: str
    name: str = Field(min_length=1, max_length=100)
    portfolio_id: int | None = None
    display_config: DisplayConfig = DisplayConfig()


class DeviceUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    portfolio_id: int | None = None
    display_config: DisplayConfig | None = None


def device_out(db: Session, d: Device) -> dict:
    rep = d.reported or {}
    registered = (d.display_config or {}).get("panel_profile") or device_rules.DEFAULT_PROFILE
    reported = rep.get("panel_profile")
    refresh = None
    if rep.get("panel_profile") and isinstance(rep.get("requested_s"), int):
        refresh = device_rules.compute_refresh(rep["panel_profile"], rep["requested_s"]).as_dict()
    return {"id": d.id, "device_uid": d.device_uid, "name": d.name, "portfolio_id": d.portfolio_id,
            "display_config": {**DEFAULT_DISPLAY, **(d.display_config or {})}, "firmware": d.firmware,
            "last_heartbeat_at": d.last_heartbeat_at, "last_fetch_at": d.last_fetch_at, "rssi": d.rssi,
            "uptime_s": d.uptime_s, "api_status": d.api_status, "data_version": d.data_version, "ip": d.ip,
            "reported": rep, "online": device_online(db, d), "refresh_check": refresh, "created_at": d.created_at,
            "panel_profile": device_panel(d), "panel_registered": registered,
            "panel_mismatch": bool(reported and reported != registered and reported != "UNKNOWN")}


@router.get("/api/v1/devices")
def list_devices(db: Session = Depends(get_db), _: User = Depends(current_admin)):
    return [device_out(db, d) for d in db.query(Device).order_by(Device.name).all()]


@router.post("/api/v1/devices", status_code=201)
def create_device(body: DeviceIn, db: Session = Depends(get_db), user: User = Depends(current_admin)):
    if not UID_RE.match(body.device_uid):
        raise HTTPException(422, "device_uid must be 3-64 characters: letters, digits, '-' or '_'")
    if db.query(Device).filter(Device.device_uid == body.device_uid).one_or_none():
        raise HTTPException(409, "device_uid already registered")
    if body.portfolio_id is not None:
        get_or_404(db, Portfolio, body.portfolio_id, "Portfolio")
    d = Device(device_uid=body.device_uid, name=body.name, portfolio_id=body.portfolio_id,
               display_config=body.display_config.model_dump())
    db.add(d)
    db.commit()
    audit(db, user.username, "device_created", "device", d.id, body.model_dump())
    return device_out(db, d)


@router.put("/api/v1/devices/{did}")
def update_device(did: int, body: DeviceUpdate, db: Session = Depends(get_db), user: User = Depends(current_admin)):
    d = get_or_404(db, Device, did, "Device")
    data = body.model_dump(exclude_unset=True)
    if "portfolio_id" in data and data["portfolio_id"] is not None:
        get_or_404(db, Portfolio, data["portfolio_id"], "Portfolio")
    if "name" in data and data["name"]:
        d.name = data["name"]
    if "portfolio_id" in data:
        d.portfolio_id = data["portfolio_id"]
    if body.display_config is not None:
        d.display_config = body.display_config.model_dump()
    db.commit()
    audit(db, user.username, "device_updated", "device", did, data)
    return device_out(db, d)


@router.delete("/api/v1/devices/{did}")
def delete_device(did: int, db: Session = Depends(get_db), user: User = Depends(current_admin)):
    d = get_or_404(db, Device, did, "Device")
    now = datetime.now(timezone.utc)
    db.query(ApiKey).filter(ApiKey.device_id == did, ApiKey.revoked_at.is_(None)).update({ApiKey.revoked_at: now})
    db.delete(d)
    db.commit()
    audit(db, user.username, "device_deleted", "device", did, {"keys_revoked": True})
    return {"ok": True}


def device_panel(d: Device) -> str:
    """Panel used for this device's pages: what its firmware reported (the real hardware), otherwise the
    module chosen at registration, otherwise the 2.9in panel."""
    reported = (d.reported or {}).get("panel_profile")
    if reported in device_rules.modules():
        return reported
    return (d.display_config or {}).get("panel_profile") or device_rules.DEFAULT_PROFILE


@router.get("/api/v1/devices/{did}/preview")
def preview_device(did: int, panel: str | None = Query(None, max_length=40), db: Session = Depends(get_db),
                   _: User = Depends(current_admin)):
    d = get_or_404(db, Device, did, "Device")
    pf = db.get(Portfolio, d.portfolio_id) if d.portfolio_id else None
    dash = dashboard_for(db, portfolio=pf, display=d.display_config or {}, device_uid=d.device_uid, device_name=d.name,
                         panel_profile=panel or device_panel(d))
    dash["panel_profile"] = device_rules.panel_spec(panel or device_panel(d))["profile"]
    return dash


# ----------------------------------------------------------------------------- API keys

class ApiKeyIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    device_id: int | None = None
    scopes: list[str] = ["device:dashboard", "device:heartbeat"]
    expires_in_days: int | None = Field(365, ge=1, le=3650)


def key_out(k: ApiKey) -> dict:
    now = datetime.now(timezone.utc)
    state = "revoked" if k.revoked_at else "expired" if (k.expires_at and k.expires_at < now) else "active"
    return {"id": k.id, "name": k.name, "prefix": f"lsk_{k.prefix}_****", "scopes": k.scopes, "device_id": k.device_id,
            "expires_at": k.expires_at, "revoked_at": k.revoked_at, "last_used_at": k.last_used_at,
            "last_used_ip": k.last_used_ip, "rotated_from_id": k.rotated_from_id, "created_at": k.created_at,
            "state": state}


@router.get("/api/v1/api-keys/scopes")
def scopes(_: User = Depends(current_admin)):
    return DEVICE_SCOPES


@router.get("/api/v1/api-keys")
def list_keys(db: Session = Depends(get_db), _: User = Depends(current_admin)):
    return [key_out(k) for k in db.query(ApiKey).order_by(ApiKey.created_at.desc()).all()]


def _create_key(db: Session, name: str, device_id: int | None, scopes_: list[str], expires_in_days: int | None,
                rotated_from: int | None = None) -> tuple[ApiKey, str]:
    bad = [s for s in scopes_ if s not in DEVICE_SCOPES]
    if bad or not scopes_:
        raise HTTPException(422, f"Invalid scopes: {bad or 'none given'}")
    if device_id is not None:
        get_or_404(db, Device, device_id, "Device")
    full, prefix, digest = generate_api_key()
    exp = datetime.now(timezone.utc) + timedelta(days=expires_in_days) if expires_in_days else None
    k = ApiKey(name=name, prefix=prefix, key_hash=digest, scopes=sorted(set(scopes_)), device_id=device_id,
               expires_at=exp, rotated_from_id=rotated_from)
    db.add(k)
    db.commit()
    return k, full


@router.post("/api/v1/api-keys", status_code=201)
def create_key(body: ApiKeyIn, db: Session = Depends(get_db), user: User = Depends(current_admin)):
    k, full = _create_key(db, body.name, body.device_id, body.scopes, body.expires_in_days)
    audit(db, user.username, "api_key_created", "api_key", k.id, {"name": k.name, "scopes": k.scopes,
                                                                    "device_id": k.device_id})
    return {**key_out(k), "key": full,
            "warning": "Copy this key now. It is shown only once and stored only as a hash."}


@router.post("/api/v1/api-keys/{kid}/revoke")
def revoke_key(kid: int, db: Session = Depends(get_db), user: User = Depends(current_admin)):
    k = get_or_404(db, ApiKey, kid, "API key")
    k.revoked_at = k.revoked_at or datetime.now(timezone.utc)
    db.commit()
    audit(db, user.username, "api_key_revoked", "api_key", kid)
    return key_out(k)


@router.post("/api/v1/api-keys/{kid}/rotate", status_code=201)
def rotate_key(kid: int, db: Session = Depends(get_db), user: User = Depends(current_admin)):
    old = get_or_404(db, ApiKey, kid, "API key")
    if old.revoked_at:
        raise HTTPException(409, "Key already revoked")
    days = None
    if old.expires_at:
        days = max(1, (old.expires_at - old.created_at).days)
    new, full = _create_key(db, old.name, old.device_id, old.scopes, days, rotated_from=old.id)
    old.revoked_at = datetime.now(timezone.utc)
    db.commit()
    audit(db, user.username, "api_key_rotated", "api_key", kid, {"new_id": new.id})
    return {**key_out(new), "key": full,
            "warning": "Old key revoked. Copy the new key now; it is shown only once."}


@router.get("/api/v1/api-keys/{kid}/logs")
def key_logs(kid: int, limit: int = 100, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    get_or_404(db, ApiKey, kid, "API key")
    rows = (db.query(ApiAccessLog).filter(ApiAccessLog.api_key_id == kid).order_by(ApiAccessLog.ts.desc())
            .limit(min(limit, 1000)).all())
    return [{"ts": r.ts, "method": r.method, "path": r.path, "status": r.status, "ip": r.ip} for r in rows]


@router.get("/api/v1/access-logs")
def all_logs(limit: int = 200, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    rows = db.query(ApiAccessLog).order_by(ApiAccessLog.ts.desc()).limit(min(limit, 1000)).all()
    return [{"ts": r.ts, "api_key_id": r.api_key_id, "method": r.method, "path": r.path, "status": r.status,
             "ip": r.ip} for r in rows]


# ----------------------------------------------------------------------------- device endpoints

def _device_for_key(db: Session, key: ApiKey) -> Device:
    if key.device_id is None:
        raise HTTPException(403, "API key is not bound to a device")
    d = db.get(Device, key.device_id)
    if d is None:
        raise HTTPException(403, "Device not found for this key")
    return d


@router.get("/api/v1/device/dashboard")
def device_dashboard(request: Request, response: Response, since: str | None = Query(None, max_length=32),
                     rows: int | None = Query(None, ge=4, le=8), summary: bool | None = None,
                     bench: bool | None = None, panel: str | None = Query(None, max_length=40),
                     db: Session = Depends(get_db),
                     key: ApiKey = Depends(require_device_key("device:dashboard"))):
    """Compact dashboard for the authenticated device. The server enforces the device's assigned
    portfolio; the device may only narrow its display options (rows/pages). `panel` is the firmware's
    compiled panel profile and selects the page layout (2.9in portrait or 4.2in landscape)."""
    d = _device_for_key(db, key)
    display = {**DEFAULT_DISPLAY, **(d.display_config or {})}
    if rows is not None:
        display["rows_per_page"] = rows
    if summary is not None:
        display["show_summary_page"] = summary
    if bench is not None:
        display["show_benchmarks_page"] = bench
    pf = db.get(Portfolio, d.portfolio_id) if d.portfolio_id else None
    if panel and panel in device_rules.panel_profiles()["profiles"] and panel != (d.reported or {}).get("panel_profile"):
        d.reported = {**(d.reported or {}), "panel_profile": panel}  # known before the first heartbeat
    dash = dashboard_for(db, portfolio=pf, display=display, device_uid=d.device_uid, device_name=d.name,
                         panel_profile=panel or device_panel(d))
    d.last_fetch_at = datetime.now(timezone.utc)
    d.ip = client_ip(request)
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    if since and since == dash["data_version"]:
        return Response(status_code=304, headers={"Cache-Control": "no-store"})
    return dash


class HeartbeatIn(BaseModel):
    firmware: str = Field("", max_length=32)
    rssi: int | None = Field(None, ge=-127, le=0)
    uptime_s: int | None = Field(None, ge=0)
    api_status: str = Field("", max_length=32)
    data_version: str = Field("", max_length=32)
    page: int | None = Field(None, ge=1, le=64)
    pages: int | None = Field(None, ge=1, le=64)
    rotation_enabled: bool | None = None
    requested_s: int | None = Field(None, ge=1, le=86400)
    effective_s: int | None = Field(None, ge=1, le=86400)
    panel_profile: str = Field("", max_length=40)
    free_heap: int | None = Field(None, ge=0)
    fetch_count: int | None = Field(None, ge=0)
    refresh_count: int | None = Field(None, ge=0)
    ntp_ok: bool | None = None
    last_error: str = Field("", max_length=200)


@router.post("/api/v1/device/heartbeat")
def device_heartbeat(body: HeartbeatIn, request: Request, db: Session = Depends(get_db),
                     key: ApiKey = Depends(require_device_key("device:heartbeat"))):
    d = _device_for_key(db, key)
    d.last_heartbeat_at = datetime.now(timezone.utc)
    d.firmware = body.firmware or d.firmware
    d.rssi = body.rssi
    d.uptime_s = body.uptime_s
    d.api_status = body.api_status or d.api_status
    d.data_version = body.data_version or d.data_version
    d.ip = client_ip(request)
    d.reported = body.model_dump()
    db.commit()
    return {"ok": True, "server_time": d.last_heartbeat_at.isoformat()}
