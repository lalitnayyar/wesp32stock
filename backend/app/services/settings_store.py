"""Runtime-tunable application settings persisted in the app_settings table."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..models import AppSetting

# key: (default, type, min, max, description)
SPEC: dict[str, tuple[Any, type, float | None, float | None, str]] = {
    "quote_refresh_s": (60, int, 15, 3600, "Central quote refresh interval (seconds)"),
    "request_timeout_s": (10, int, 1, 60, "Provider request timeout (seconds)"),
    "retry_attempts": (3, int, 0, 6, "Retries per symbol after the first failure"),
    "backoff_base_s": (1.0, float, 0.1, 30, "Exponential backoff base delay (seconds)"),
    "market_hours_optimization": (True, bool, None, None, "Poll closed markets less often"),
    "closed_market_poll_s": (900, int, 60, 86400, "Poll interval for closed markets (seconds)"),
    "history_enabled": (True, bool, None, None, "Download daily price history"),
    "history_days": (365, int, 30, 1825, "Days of daily history to keep"),
    "stale_after_s": (900, int, 60, 86400, "Quote age after which it is labelled stale (seconds)"),
    "heartbeat_timeout_s": (300, int, 30, 86400, "Device is offline after this many seconds without heartbeat"),
    "timezone": ("Asia/Dubai", str, None, None, "Default display timezone"),
    "device_rate_limit_per_min": (30, int, 1, 600, "Device API requests per key per minute"),
    "demo_data_loaded": (False, bool, None, None, "Internal: demo data has been seeded"),
}

PUBLIC_KEYS = [k for k in SPEC if k != "demo_data_loaded"]


class SettingError(ValueError):
    pass


def coerce(key: str, value: Any) -> Any:
    if key not in SPEC:
        raise SettingError(f"Unknown setting {key}")
    default, typ, lo, hi, _ = SPEC[key]
    if typ is bool:
        if not isinstance(value, bool):
            raise SettingError(f"{key} must be true or false")
        return value
    if typ is str:
        if not isinstance(value, str) or not value.strip() or len(value) > 64:
            raise SettingError(f"{key} must be a non-empty string")
        if key == "timezone":
            from zoneinfo import ZoneInfo
            try:
                ZoneInfo(value)
            except Exception as exc:
                raise SettingError(f"Unknown timezone {value}") from exc
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SettingError(f"{key} must be a number")
    if typ is int and (isinstance(value, float) and not value.is_integer()):
        raise SettingError(f"{key} must be a whole number")
    value = typ(value)
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        raise SettingError(f"{key} must be between {lo} and {hi}")
    return value


def get(db: Session, key: str) -> Any:
    row = db.get(AppSetting, key)
    return SPEC[key][0] if row is None else row.value


def get_all(db: Session) -> dict[str, Any]:
    rows = {r.key: r.value for r in db.query(AppSetting).all()}
    return {k: rows.get(k, SPEC[k][0]) for k in PUBLIC_KEYS}


def set_many(db: Session, values: dict[str, Any]) -> dict[str, Any]:
    clean = {k: coerce(k, v) for k, v in values.items()}
    for k, v in clean.items():
        row = db.get(AppSetting, k)
        if row is None:
            db.add(AppSetting(key=k, value=v))
        else:
            row.value = v
    db.commit()
    return clean


def describe() -> list[dict]:
    return [{"key": k, "default": SPEC[k][0], "type": SPEC[k][1].__name__, "min": SPEC[k][2], "max": SPEC[k][3],
             "description": SPEC[k][4]} for k in PUBLIC_KEYS]
