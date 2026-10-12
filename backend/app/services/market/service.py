"""Central quote polling: one provider request per symbol per cycle, shared by every device.

Retries use exponential backoff with jitter. The last valid quote is retained on failure and is
labelled stale once older than `stale_after_s`.
"""
from __future__ import annotations

import logging
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from ...core.config import get_settings
from ...models import PriceHistory, Quote, Stock
from .. import settings_store
from .base import MarketDataProvider, ProviderError, QuoteData, SymbolNotFound
from .hours import market_for_symbol, market_state

log = logging.getLogger(__name__)

_provider: MarketDataProvider | None = None
_lock = threading.Lock()


def get_provider() -> MarketDataProvider:
    global _provider
    if _provider is None:
        name = get_settings().market_provider
        if name == "fixture":
            from .fixture import FixtureProvider
            _provider = FixtureProvider()
        else:
            from .yahoo import YahooProvider
            _provider = YahooProvider()
    return _provider


def set_provider(p: MarketDataProvider | None) -> None:
    """Test hook."""
    global _provider
    _provider = p


@dataclass
class PollStats:
    started_at: datetime | None = None
    finished_at: datetime | None = None
    last_success_at: datetime | None = None
    symbols: int = 0
    ok: int = 0
    failed: int = 0
    skipped: int = 0
    errors: dict[str, str] = field(default_factory=dict)


LAST_POLL = PollStats()


def fetch_with_retry(provider: MarketDataProvider, symbol: str, attempts: int, timeout_s: float, backoff_s: float,
                     sleep=time.sleep) -> QuoteData:
    last_exc: ProviderError | None = None
    for attempt in range(attempts + 1):
        ex = ThreadPoolExecutor(max_workers=1)
        try:
            return ex.submit(provider.get_quote, symbol).result(timeout=timeout_s)
        except FutTimeout:
            last_exc = ProviderError(f"{symbol}: timed out after {timeout_s}s")
        except ProviderError as exc:
            last_exc = exc
            if not exc.retryable:
                raise
        finally:
            ex.shutdown(wait=False)  # never block on a hung provider call
        if attempt < attempts:
            delay = backoff_s * (2 ** attempt) * (1 + random.random() * 0.25)
            if getattr(last_exc, "code", "") == "rate_limited":
                delay *= 4
            sleep(delay)
    assert last_exc is not None
    raise last_exc


def _should_poll(stock: Stock, quote: Quote | None, now: datetime, cfg: dict) -> bool:
    if not cfg["market_hours_optimization"] or quote is None or quote.last_success_at is None:
        return True
    mkt = stock.market or market_for_symbol(stock.ticker)
    if market_state(mkt, now) != "CLOSED":
        return True
    return (now - quote.last_success_at).total_seconds() >= cfg["closed_market_poll_s"]


def apply_quote(db: Session, stock: Stock, q: QuoteData, now: datetime) -> Quote:
    quote = stock.quote or Quote(stock_id=stock.id)
    quote.price = q.price
    quote.prev_close = q.prev_close
    if q.prev_close:
        quote.change = q.price - q.prev_close
        quote.change_pct = (quote.change / q.prev_close * 100).quantize(Decimal("0.0001"))
    else:
        quote.change = None
        quote.change_pct = None
    quote.currency = q.currency or stock.currency
    quote.market_state = q.market_state or market_state(stock.market or market_for_symbol(stock.ticker), now)
    quote.delayed = q.delayed
    quote.quote_time = q.quote_time or now
    quote.last_poll_at = now
    quote.last_success_at = now
    quote.last_error = None
    quote.consecutive_failures = 0
    if stock.quote is None:
        db.add(quote)
        stock.quote = quote
    stock.last_update = now
    stock.data_quality = "ok"
    return quote


def poll_once(db: Session, provider: MarketDataProvider | None = None, sleep=time.sleep,
              only_ids: list[int] | None = None, wait_s: float = 0) -> PollStats:
    """Poll every active stock once. Safe to call from scheduler or the 'refresh now' endpoint
    (manual refreshes pass wait_s so they wait for an in-progress scheduled poll)."""
    acquired = _lock.acquire(timeout=wait_s) if wait_s > 0 else _lock.acquire(blocking=False)
    if not acquired:
        log.info("quote poll already running; skipping")
        return LAST_POLL
    try:
        provider = provider or get_provider()
        cfg = {k: settings_store.get(db, k) for k in
               ("retry_attempts", "request_timeout_s", "backoff_base_s", "market_hours_optimization",
                "closed_market_poll_s", "stale_after_s")}
        now = datetime.now(timezone.utc)
        stats = PollStats(started_at=now)
        q = db.query(Stock).filter(Stock.active.is_(True))
        if only_ids:
            q = q.filter(Stock.id.in_(only_ids))
        for stock in q.all():
            stats.symbols += 1
            if not only_ids and not _should_poll(stock, stock.quote, now, cfg):
                stats.skipped += 1
                continue
            try:
                data = fetch_with_retry(provider, stock.ticker, cfg["retry_attempts"], cfg["request_timeout_s"],
                                        cfg["backoff_base_s"], sleep=sleep)
                apply_quote(db, stock, data, datetime.now(timezone.utc))
                stats.ok += 1
            except ProviderError as exc:
                stats.failed += 1
                stats.errors[stock.ticker] = str(exc)[:200]
                quote = stock.quote
                if quote is None:
                    quote = Quote(stock_id=stock.id)
                    db.add(quote)
                    stock.quote = quote
                quote.last_poll_at = datetime.now(timezone.utc)
                quote.last_error = f"{getattr(exc, 'code', 'error')}: {str(exc)[:200]}"
                quote.consecutive_failures = (quote.consecutive_failures or 0) + 1
                if isinstance(exc, SymbolNotFound):
                    stock.data_quality = "unavailable"
                elif quote.last_success_at and (now - quote.last_success_at).total_seconds() > cfg["stale_after_s"]:
                    stock.data_quality = "stale"
                log.warning("quote failed for %s: %s", stock.ticker, exc)
            db.commit()
        # Mark aged quotes stale even when the poll was skipped.
        for stock in db.query(Stock).filter(Stock.active.is_(True)).all():
            if stock.quote and stock.quote.last_success_at and stock.data_quality == "ok":
                if (now - stock.quote.last_success_at).total_seconds() > cfg["stale_after_s"]:
                    stock.data_quality = "stale"
        db.commit()
        stats.finished_at = datetime.now(timezone.utc)
        if stats.ok:
            stats.last_success_at = stats.finished_at
        else:
            stats.last_success_at = LAST_POLL.last_success_at
        LAST_POLL.__dict__.update(stats.__dict__)
        return stats
    finally:
        _lock.release()


def is_stale(quote: Quote | None, stale_after_s: int, now: datetime | None = None) -> bool:
    if quote is None or quote.last_success_at is None:
        return True
    now = now or datetime.now(timezone.utc)
    return (now - quote.last_success_at).total_seconds() > stale_after_s


def refresh_history(db: Session, provider: MarketDataProvider | None = None) -> dict[str, int | str]:
    provider = provider or get_provider()
    days = settings_store.get(db, "history_days")
    out: dict[str, int | str] = {}
    for stock in db.query(Stock).filter(Stock.active.is_(True)).all():
        try:
            rows = provider.get_history(stock.ticker, days)
        except ProviderError as exc:
            out[stock.ticker] = f"error: {exc}"
            continue
        existing = {h.day: h for h in db.query(PriceHistory).filter(PriceHistory.stock_id == stock.id)}
        for day, close in rows:
            if day in existing:
                existing[day].close = close
            else:
                db.add(PriceHistory(stock_id=stock.id, day=day, close=close))
        cutoff = date.today() - timedelta(days=days + 7)
        db.query(PriceHistory).filter(PriceHistory.stock_id == stock.id, PriceHistory.day < cutoff).delete()
        db.commit()
        out[stock.ticker] = len(rows)
    return out
