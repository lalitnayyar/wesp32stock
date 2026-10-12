from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models import Quote, Stock
from app.services import settings_store
from app.services.market import service as market
from app.services.market.base import MarketDataProvider, ProviderError, QuoteData, RateLimited, SymbolNotFound
from app.services.market.hours import market_for_symbol, market_state


class FlakyProvider(MarketDataProvider):
    name = "flaky"

    def __init__(self, failures: int, exc=ProviderError):
        self.failures, self.exc, self.calls = failures, exc, 0

    def get_quote(self, symbol):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.exc(f"{symbol} boom")
        return QuoteData(symbol, Decimal("10.5"), Decimal("10"), "USD", datetime.now(timezone.utc))

    def validate_symbol(self, symbol):
        raise NotImplementedError

    def get_history(self, symbol, days):
        return []


def test_retry_with_exponential_backoff():
    sleeps = []
    p = FlakyProvider(2)
    q = market.fetch_with_retry(p, "X", attempts=3, timeout_s=5, backoff_s=1.0, sleep=sleeps.append)
    assert q.price == Decimal("10.5") and p.calls == 3
    assert len(sleeps) == 2 and 1.0 <= sleeps[0] <= 1.25 and 2.0 <= sleeps[1] <= 2.5


def test_rate_limit_backs_off_longer_then_gives_up():
    sleeps = []
    p = FlakyProvider(10, RateLimited)
    with pytest.raises(RateLimited):
        market.fetch_with_retry(p, "X", attempts=1, timeout_s=5, backoff_s=1.0, sleep=sleeps.append)
    assert p.calls == 2 and sleeps[0] >= 4.0


def test_unavailable_symbol_not_retried():
    p = FlakyProvider(10, SymbolNotFound)
    with pytest.raises(SymbolNotFound):
        market.fetch_with_retry(p, "X", attempts=3, timeout_s=5, backoff_s=0, sleep=lambda s: None)
    assert p.calls == 1


def test_poll_keeps_last_valid_quote_and_marks_stale(db):
    st = Stock(ticker="AAPL", currency="USD", market="US")
    db.add(st)
    db.commit()
    market.poll_once(db, provider=FlakyProvider(0), sleep=lambda s: None)
    db.refresh(st)
    assert st.quote.price == Decimal("10.5") and st.quote.change_pct == Decimal("5.0000") and st.data_quality == "ok"
    # age the quote, then fail every attempt
    st.quote.last_success_at = datetime.now(timezone.utc) - timedelta(hours=2)
    db.commit()
    stats = market.poll_once(db, provider=FlakyProvider(99), sleep=lambda s: None, only_ids=[st.id])
    db.refresh(st)
    assert stats.failed == 1 and st.quote.price == Decimal("10.5")
    assert st.data_quality == "stale" and st.quote.last_error.startswith("provider_error")
    assert st.quote.consecutive_failures == 1
    assert market.is_stale(st.quote, 900)


def test_unavailable_symbol_flagged(db):
    db.add(Stock(ticker="NOPE", currency="USD"))
    db.commit()
    market.poll_once(db, provider=FlakyProvider(9, SymbolNotFound), sleep=lambda s: None)
    st = db.query(Stock).filter_by(ticker="NOPE").one()
    assert st.data_quality == "unavailable" and st.quote.price is None


def test_market_hours_optimisation_skips_closed_market(db):
    st = Stock(ticker="EMAAR.AE", currency="AED", market="DFM")
    db.add(st)
    db.flush()
    now = datetime.now(timezone.utc)
    db.add(Quote(stock_id=st.id, price=Decimal(8), last_success_at=now - timedelta(seconds=60)))
    db.commit()
    p = FlakyProvider(0)
    cfg = {"market_hours_optimization": True, "closed_market_poll_s": 900}
    sat = datetime(2026, 10, 10, 8, 0, tzinfo=timezone.utc)  # Saturday
    st.quote.last_success_at = sat - timedelta(seconds=60)
    assert market._should_poll(st, st.quote, sat, cfg) is False
    st.quote.last_success_at = sat - timedelta(seconds=1000)
    assert market._should_poll(st, st.quote, sat, cfg) is True
    assert p.calls == 0


def test_market_state_and_suffixes():
    assert market_for_symbol("EMAAR.AE") == "DFM" and market_for_symbol("AAPL") == "US"
    assert market_for_symbol("^GSPC") == "INDEX"
    # Monday 2026-10-12 15:00 UTC = 11:00 New York -> open; 03:00 UTC -> closed
    assert market_state("US", datetime(2026, 10, 12, 15, 0, tzinfo=timezone.utc)) == "OPEN"
    assert market_state("US", datetime(2026, 10, 12, 3, 0, tzinfo=timezone.utc)) == "CLOSED"
    assert market_state("DFM", datetime(2026, 10, 12, 7, 0, tzinfo=timezone.utc)) == "OPEN"   # 11:00 Dubai
    assert market_state("DFM", datetime(2026, 10, 10, 7, 0, tzinfo=timezone.utc)) == "CLOSED"  # Saturday


def test_refresh_interval_default_60_and_persisted(admin, db):
    assert settings_store.get(db, "quote_refresh_s") == 60
    r = admin.put("/api/v1/settings", json={"quote_refresh_s": 120})
    assert r.status_code == 200 and r.json()["values"]["quote_refresh_s"] == 120
    db.expire_all()
    assert settings_store.get(db, "quote_refresh_s") == 120
    assert admin.put("/api/v1/settings", json={"quote_refresh_s": 5}).status_code == 422
    assert admin.put("/api/v1/settings", json={"quote_refresh_s": "abc"}).status_code == 422
    status = admin.get("/api/v1/market/status").json()
    assert status["quote_refresh_s"] == 120 and "last_poll" in status


def test_market_status_observable_after_refresh(admin):
    admin.post("/api/v1/stocks", json={"ticker": "AAPL"})
    r = admin.post("/api/v1/market/refresh")
    assert r.status_code == 200 and r.json()["ok"] >= 1
    st = admin.get("/api/v1/market/status").json()
    aapl = next(s for s in st["symbols"] if s["ticker"] == "AAPL")
    assert aapl["last_success_at"] and aapl["stale"] is False and st["last_poll"]["ok"] >= 1
