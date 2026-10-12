from __future__ import annotations

import re
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.security import current_admin
from ..models import Benchmark, PriceHistory, Stock, Transaction, User
from ..services import analytics, settings_store
from ..services.audit import audit
from ..services.market import service as market
from ..services.market.base import ProviderError, SymbolNotFound
from ..services.market.hours import market_for_symbol
from .common import get_or_404

router = APIRouter(prefix="/api/v1", tags=["stocks"])

SYMBOL_RE = re.compile(r"^[A-Z0-9^][A-Z0-9.\-^=]{0,31}$")
EXCHANGE_SUFFIX_HINTS = {
    "DFM": ".AE", "ADX": ".AD", "NASDAQ_DUBAI": ".AE (varies)", "NYSE": "(none)", "NASDAQ": "(none)",
}


def normalize_symbol(sym: str) -> str:
    sym = (sym or "").strip().upper()
    if not SYMBOL_RE.match(sym):
        raise HTTPException(422, "Invalid symbol format. Use the provider symbol incl. exchange suffix, e.g. EMAAR.AE")
    return sym


class StockIn(BaseModel):
    ticker: str
    company: str = ""
    kind: str = Field("equity", pattern="^(equity|etf|index|fx)$")
    exchange: str = ""
    market: str = ""
    currency: str = ""
    sector: str = ""
    industry: str = ""
    country: str = ""
    notes: str = ""
    active: bool = True
    skip_validation: bool = False


class StockUpdate(BaseModel):
    company: str | None = None
    exchange: str | None = None
    market: str | None = None
    currency: str | None = None
    sector: str | None = None
    industry: str | None = None
    country: str | None = None
    notes: str | None = None
    active: bool | None = None


def stock_out(st: Stock, stale_after: int) -> dict:
    q = st.quote
    return {
        "id": st.id, "ticker": st.ticker, "company": st.company, "kind": st.kind, "exchange": st.exchange,
        "market": st.market, "currency": st.currency, "sector": st.sector, "industry": st.industry,
        "country": st.country, "provider": st.provider, "active": st.active, "last_update": st.last_update,
        "data_quality": st.data_quality, "notes": st.notes,
        "quote": None if q is None else {
            "price": analytics.s(q.price, 4), "prev_close": analytics.s(q.prev_close, 4),
            "change": analytics.s(q.change, 4), "change_pct": analytics.s(q.change_pct),
            "currency": q.currency, "market_state": q.market_state, "delayed": q.delayed,
            "quote_time": q.quote_time, "last_poll_at": q.last_poll_at, "last_success_at": q.last_success_at,
            "last_error": q.last_error, "stale": market.is_stale(q, stale_after),
        },
    }


@router.get("/stocks")
def list_stocks(q: str = "", active: bool | None = None, kind: str | None = None, db: Session = Depends(get_db),
                _: User = Depends(current_admin)):
    query = db.query(Stock)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Stock.ticker.ilike(like), Stock.company.ilike(like)))
    if active is not None:
        query = query.filter(Stock.active.is_(active))
    if kind:
        query = query.filter(Stock.kind == kind)
    stale_after = settings_store.get(db, "stale_after_s")
    return [stock_out(s, stale_after) for s in query.order_by(Stock.ticker).all()]


@router.post("/stocks/validate")
def validate_symbol(body: dict, _: User = Depends(current_admin)):
    sym = normalize_symbol(body.get("ticker", ""))
    try:
        info = market.get_provider().validate_symbol(sym)
    except SymbolNotFound as exc:
        return {"valid": False, "ticker": sym, "message": str(exc),
                "hint": "Check the exchange suffix: " + ", ".join(f"{k}: {v}" for k, v in EXCHANGE_SUFFIX_HINTS.items())}
    except ProviderError as exc:
        raise HTTPException(502, f"Provider unavailable: {exc}")
    return {"valid": True, "ticker": sym, "info": info.__dict__, "market": market_for_symbol(sym)}


@router.post("/stocks", status_code=201)
def create_stock(body: StockIn, db: Session = Depends(get_db), user: User = Depends(current_admin)):
    sym = normalize_symbol(body.ticker)
    if db.query(Stock).filter(Stock.ticker == sym).one_or_none():
        raise HTTPException(409, f"{sym} already exists")
    data = body.model_dump(exclude={"skip_validation", "ticker"})
    quality = "unvalidated"
    if not body.skip_validation:
        try:
            info = market.get_provider().validate_symbol(sym)
        except SymbolNotFound as exc:
            raise HTTPException(422, f"Unsupported symbol: {exc}")
        except ProviderError as exc:
            raise HTTPException(502, f"Provider unavailable, retry or use skip_validation: {exc}")
        for k in ("company", "exchange", "currency", "sector", "industry", "country", "kind"):
            if not data.get(k) or (k == "kind" and data[k] == "equity"):
                data[k] = getattr(info, k) or data.get(k)
        quality = "ok"
    data["market"] = data.get("market") or market_for_symbol(sym)
    data["currency"] = (data.get("currency") or "USD").upper()
    from ..core.config import get_settings
    st = Stock(ticker=sym, provider=get_settings().market_provider, data_quality=quality, **data)
    db.add(st)
    db.commit()
    audit(db, user.username, "stock_created", "stock", st.id, {"ticker": sym})
    return stock_out(st, settings_store.get(db, "stale_after_s"))


@router.get("/stocks/{stock_id}")
def get_stock(stock_id: int, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    return stock_out(get_or_404(db, Stock, stock_id, "Stock"), settings_store.get(db, "stale_after_s"))


@router.put("/stocks/{stock_id}")
def update_stock(stock_id: int, body: StockUpdate, db: Session = Depends(get_db), user: User = Depends(current_admin)):
    st = get_or_404(db, Stock, stock_id, "Stock")
    changes = body.model_dump(exclude_none=True)
    if "currency" in changes:
        changes["currency"] = changes["currency"].upper()
    for k, v in changes.items():
        setattr(st, k, v)
    db.commit()
    audit(db, user.username, "stock_updated", "stock", st.id, changes)
    return stock_out(st, settings_store.get(db, "stale_after_s"))


@router.delete("/stocks/{stock_id}")
def delete_stock(stock_id: int, db: Session = Depends(get_db), user: User = Depends(current_admin)):
    st = get_or_404(db, Stock, stock_id, "Stock")
    if db.query(Transaction).filter(Transaction.stock_id == st.id).count():
        raise HTTPException(409, "Stock has transactions; deactivate it instead")
    db.query(Benchmark).filter(Benchmark.stock_id == st.id).delete()
    db.delete(st)
    db.commit()
    audit(db, user.username, "stock_deleted", "stock", stock_id, {"ticker": st.ticker})
    return {"ok": True}


@router.post("/stocks/{stock_id}/refresh")
def refresh_stock(stock_id: int, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    get_or_404(db, Stock, stock_id, "Stock")
    stats = market.poll_once(db, only_ids=[stock_id], wait_s=60)
    return {"ok": stats.ok, "failed": stats.failed, "errors": stats.errors}


@router.get("/stocks/{stock_id}/history")
def stock_history(stock_id: int, days: int = 180, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    get_or_404(db, Stock, stock_id, "Stock")
    since = date.today() - timedelta(days=min(max(days, 7), 1825))
    rows = (db.query(PriceHistory).filter(PriceHistory.stock_id == stock_id, PriceHistory.day >= since)
            .order_by(PriceHistory.day).all())
    return [{"date": r.day.isoformat(), "close": analytics.s(r.close, 4)} for r in rows]


# ----------------------------------------------------------------------------- benchmarks

class BenchmarkIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    ticker: str
    active: bool = True
    sort_order: int = 0


@router.get("/benchmarks")
def list_benchmarks(db: Session = Depends(get_db), _: User = Depends(current_admin)):
    perf = {b["id"]: b for b in analytics.benchmarks(db)}
    out = []
    for b in db.query(Benchmark).order_by(Benchmark.sort_order).all():
        out.append({"id": b.id, "name": b.name, "ticker": b.stock.ticker, "stock_id": b.stock_id, "active": b.active,
                    "sort_order": b.sort_order, "notes": b.stock.notes, "data_quality": b.stock.data_quality,
                    "performance": perf.get(b.id)})
    return out


@router.post("/benchmarks", status_code=201)
def create_benchmark(body: BenchmarkIn, db: Session = Depends(get_db), user: User = Depends(current_admin)):
    sym = normalize_symbol(body.ticker)
    st = db.query(Stock).filter(Stock.ticker == sym).one_or_none()
    if st is None:
        try:
            info = market.get_provider().validate_symbol(sym)
        except ProviderError as exc:
            raise HTTPException(422, f"Benchmark symbol not supported by provider: {exc}")
        st = Stock(ticker=sym, company=info.company, kind="index", market="INDEX", currency=info.currency or "USD",
                   exchange=info.exchange, data_quality="ok")
        db.add(st)
        db.flush()
    b = Benchmark(name=body.name, stock_id=st.id, active=body.active, sort_order=body.sort_order)
    st.active = st.active or body.active
    db.add(b)
    db.commit()
    audit(db, user.username, "benchmark_created", "benchmark", b.id, {"ticker": sym})
    return {"id": b.id}


@router.put("/benchmarks/{bid}")
def update_benchmark(bid: int, body: dict, db: Session = Depends(get_db), user: User = Depends(current_admin)):
    b = get_or_404(db, Benchmark, bid, "Benchmark")
    if "name" in body:
        b.name = str(body["name"])[:64]
    if "sort_order" in body:
        b.sort_order = int(body["sort_order"])
    if "active" in body:
        if body["active"] and not b.active:
            try:
                market.get_provider().validate_symbol(b.stock.ticker)
            except ProviderError as exc:
                raise HTTPException(422, f"Cannot activate: symbol not supported by provider ({exc})")
            b.stock.data_quality = "ok"
            b.stock.active = True
        b.active = bool(body["active"])
    db.commit()
    audit(db, user.username, "benchmark_updated", "benchmark", bid, body)
    return {"ok": True}


@router.delete("/benchmarks/{bid}")
def delete_benchmark(bid: int, db: Session = Depends(get_db), user: User = Depends(current_admin)):
    b = get_or_404(db, Benchmark, bid, "Benchmark")
    db.delete(b)
    db.commit()
    audit(db, user.username, "benchmark_deleted", "benchmark", bid)
    return {"ok": True}
