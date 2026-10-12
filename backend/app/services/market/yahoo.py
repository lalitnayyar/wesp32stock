"""Yahoo Finance provider via yfinance. Yahoo data is unofficial, may be delayed and is subject to
Yahoo's terms; the operator is responsible for compliance."""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from decimal import Decimal

from .base import MarketDataProvider, ProviderError, QuoteData, RateLimited, SymbolInfo, SymbolNotFound

log = logging.getLogger(__name__)


def _dec(v) -> Decimal | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return Decimal(repr(f))


def _wrap(exc: Exception, symbol: str) -> ProviderError:
    name = type(exc).__name__
    text = str(exc)
    if "RateLimit" in name or "Too Many Requests" in text or "429" in text:
        return RateLimited(f"{symbol}: rate limited by Yahoo")
    if "delisted" in text.lower() or "not found" in text.lower() or "404" in text:
        return SymbolNotFound(f"{symbol}: symbol not found or unsupported")
    return ProviderError(f"{symbol}: {name}: {text[:150]}")


class YahooProvider(MarketDataProvider):
    name = "yahoo"

    def __init__(self) -> None:
        import yfinance  # noqa: F401  (import lazily so tests without network still import the module)

    def get_quote(self, symbol: str) -> QuoteData:
        import yfinance as yf
        try:
            fi = yf.Ticker(symbol).fast_info
            price = _dec(fi.last_price)
            prev = _dec(fi.previous_close)
            currency = fi.currency or ""
        except Exception as exc:  # yfinance raises many types
            raise _wrap(exc, symbol) from exc
        if price is None:
            raise SymbolNotFound(f"{symbol}: no price returned")
        return QuoteData(symbol=symbol, price=price, prev_close=prev, currency=currency.upper(),
                         quote_time=datetime.now(timezone.utc), delayed=True)

    def validate_symbol(self, symbol: str) -> SymbolInfo:
        import yfinance as yf
        try:
            t = yf.Ticker(symbol)
            info = t.info or {}
        except Exception as exc:
            raise _wrap(exc, symbol) from exc
        if not info or (info.get("regularMarketPrice") is None and info.get("previousClose") is None
                        and info.get("currentPrice") is None):
            raise SymbolNotFound(f"{symbol}: symbol not found or unsupported by Yahoo")
        qt = (info.get("quoteType") or "EQUITY").lower()
        kind = {"equity": "equity", "etf": "etf", "index": "index", "currency": "fx"}.get(qt, "equity")
        return SymbolInfo(
            symbol=symbol,
            company=info.get("longName") or info.get("shortName") or symbol,
            exchange=info.get("fullExchangeName") or info.get("exchange") or "",
            currency=(info.get("currency") or "").upper(),
            sector=info.get("sector") or "",
            industry=info.get("industry") or "",
            country=info.get("country") or "",
            kind=kind,
        )

    def get_history(self, symbol: str, days: int) -> list[tuple[date, Decimal]]:
        import yfinance as yf
        period = "1y" if days <= 366 else "5y"
        try:
            df = yf.Ticker(symbol).history(period=period, interval="1d", auto_adjust=False)
        except Exception as exc:
            raise _wrap(exc, symbol) from exc
        out: list[tuple[date, Decimal]] = []
        for idx, row in df.tail(days).iterrows():
            c = _dec(row.get("Close"))
            if c is not None:
                out.append((idx.date(), c))
        return out
