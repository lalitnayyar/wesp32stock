"""Approximate regular trading hours per market (holidays are NOT modelled; status is labelled approximate)."""
from __future__ import annotations

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

# Yahoo exchange suffix -> market code. Mapping is a best-effort default: the admin can override
# `market` per stock, and every new symbol is validated against the provider before use.
SUFFIX_MARKET = {
    "": "US",
    "AE": "DFM",      # Yahoo: Dubai Financial Market symbols e.g. EMAAR.AE
    "AD": "ADX",      # Abu Dhabi suffix: verify per symbol with the provider
}

MARKETS = {
    "US": {"tz": "America/New_York", "open": time(9, 30), "close": time(16, 0), "days": {0, 1, 2, 3, 4}},
    "DFM": {"tz": "Asia/Dubai", "open": time(10, 0), "close": time(15, 0), "days": {0, 1, 2, 3, 4}},
    "ADX": {"tz": "Asia/Dubai", "open": time(10, 0), "close": time(15, 0), "days": {0, 1, 2, 3, 4}},
    "NASDAQ_DUBAI": {"tz": "Asia/Dubai", "open": time(10, 0), "close": time(15, 0), "days": {0, 1, 2, 3, 4}},
}


def market_for_symbol(symbol: str) -> str:
    if symbol.startswith("^") or symbol.endswith("=X"):
        return "INDEX" if symbol.startswith("^") else "FX"
    suffix = symbol.rsplit(".", 1)[1].upper() if "." in symbol else ""
    return SUFFIX_MARKET.get(suffix, "OTHER")


def market_state(market: str, now: datetime | None = None) -> str:
    """OPEN | CLOSED | UNKNOWN (approximate, regular session only)."""
    spec = MARKETS.get(market)
    if spec is None:
        return "UNKNOWN"
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(ZoneInfo(spec["tz"]))
    if local.weekday() not in spec["days"]:
        return "CLOSED"
    return "OPEN" if spec["open"] <= local.time() < spec["close"] else "CLOSED"
