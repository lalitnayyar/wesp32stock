"""Shared ESP32/simulator rules: config validation and hardware-safe refresh calculation.

Mirrors firmware/LalitStockFirmware/rotation.h and frontend/src/sim/rules.ts. All three
implementations are tested against shared/test_vectors/*.json.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import Any

from ..core.config import get_settings


@lru_cache
def load_shared(name: str) -> dict:
    path = get_settings().shared_dir / name
    return json.loads(path.read_text(encoding="utf-8"))


def config_fields() -> dict:
    return load_shared("device_config.json")["fields"]


def panel_profiles() -> dict:
    return load_shared("panel_profiles.json")


def layout() -> dict:
    return load_shared("layout.json")


@dataclass
class RefreshResult:
    profile: str
    profile_label: str
    requested_s: int
    effective_s: int
    min_safe_s: int
    refresh_gap_s: int
    clamped: bool
    fallback: bool
    verified: bool
    reason: str
    evidence: str

    def as_dict(self) -> dict:
        return asdict(self)


def compute_refresh(profile_name: str, requested_s: int) -> RefreshResult:
    data = panel_profiles()
    prof = data["profiles"].get(profile_name)
    if prof is None:
        fb = int(data["fallback_s"])
        min_safe, gap, fallback = fb, fb, True
        label, verified, evidence = "Unknown panel/driver", False, "No verified timing for this profile."
    else:
        gap = math.ceil(prof["full_refresh_ms"] * (100 + prof["safety_margin_pct"]) / 100 / 1000)
        min_safe = gap + prof["min_dwell_s"]
        fallback = False
        label, verified, evidence = prof["label"], bool(prof["verified"]), prof["evidence"]
    effective = max(requested_s, min_safe)
    clamped = effective != requested_s
    if fallback:
        reason = (f"Panel timing unknown: conservative fallback minimum of {min_safe} s applied."
                  if clamped else f"Panel timing unknown; requested {requested_s} s is above the {min_safe} s fallback minimum.")
    elif clamped:
        prof = data["profiles"][profile_name]
        reason = (f"Requested {requested_s} s is below the hardware-safe minimum of {min_safe} s: "
                  f"a full refresh takes up to {prof['full_refresh_ms'] / 1000:g} s "
                  f"(+{prof['safety_margin_pct']}% margin) plus {prof['min_dwell_s']} s minimum reading time.")
    else:
        reason = f"Requested {requested_s} s is at or above the hardware-safe minimum of {min_safe} s."
    return RefreshResult(profile_name, label, requested_s, effective, min_safe, gap, clamped, fallback, verified, reason, evidence)


def validate_field(name: str, value: Any) -> tuple[Any, bool]:
    """Return (sanitized_value, ok). Invalid values are clamped or replaced by the default."""
    spec = config_fields()[name]
    t = spec["type"]
    default = spec["default"]
    if t == "bool":
        if isinstance(value, bool):
            return value, True
        return default, False
    if t == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            return default, False
        if value < spec["min"]:
            return spec["min"], False
        if value > spec["max"]:
            return spec["max"], False
        return value, True
    if t == "enum":
        return (value, True) if value in spec["values"] else (default, False)
    if t == "string":
        if not isinstance(value, str) or not value or len(value) > spec["max_len"]:
            return default, False
        return value, True
    raise ValueError(f"unknown field type {t}")


def default_config() -> dict:
    return {k: v["default"] for k, v in config_fields().items()}


def validate_config(raw: dict) -> tuple[dict, dict[str, str]]:
    """Validate a full device config. Unknown keys are ignored. Returns (config, warnings)."""
    cfg = default_config()
    warnings: dict[str, str] = {}
    for key in cfg:
        if key in raw:
            val, ok = validate_field(key, raw[key])
            cfg[key] = val
            if not ok:
                warnings[key] = f"Invalid value {raw[key]!r}; using {val!r}"
    return cfg, warnings
