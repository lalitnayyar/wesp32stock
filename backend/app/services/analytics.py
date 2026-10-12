"""Portfolio analytics. Backend calculations are authoritative (AI only receives these results).

All money values are returned as strings to preserve Decimal precision over JSON.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from ..models import Benchmark, Portfolio, PriceHistory, Stock, Transaction
from . import settings_store
from .ledger import ZERO, compute_positions
from .market.service import is_stale

# Fixed currency pegs used only when no live FX quote exists (documented fallback).
PEGS_TO_USD = {"USD": Decimal("1"), "AED": Decimal("0.272294"), "SAR": Decimal("0.266667")}


def s(v: Decimal | None, places: int = 2) -> str | None:
    if v is None:
        return None
    return str(v.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))


def fx_rate(db: Session, from_ccy: str, to_ccy: str) -> tuple[Decimal | None, str]:
    """Return (rate, source). rate converts an amount in from_ccy into to_ccy."""
    from_ccy, to_ccy = (from_ccy or "").upper(), (to_ccy or "").upper()
    if from_ccy == to_ccy or not from_ccy:
        return Decimal(1), "same"
    direct = db.query(Stock).filter(Stock.ticker == f"{from_ccy}{to_ccy}=X").one_or_none()
    if direct and direct.quote and direct.quote.price:
        return direct.quote.price, "live"
    inverse = db.query(Stock).filter(Stock.ticker == f"{to_ccy}{from_ccy}=X").one_or_none()
    if inverse and inverse.quote and inverse.quote.price:
        return Decimal(1) / inverse.quote.price, "live"
    if from_ccy in PEGS_TO_USD and to_ccy in PEGS_TO_USD:
        return PEGS_TO_USD[from_ccy] / PEGS_TO_USD[to_ccy], "peg"
    return None, "missing"


def portfolio_transactions(db: Session, portfolio_id: int) -> list[Transaction]:
    return db.query(Transaction).filter(Transaction.portfolio_id == portfolio_id).all()


def portfolio_summary(db: Session, portfolio: Portfolio, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    stale_after = settings_store.get(db, "stale_after_s")
    base = portfolio.base_currency
    ledger = compute_positions(portfolio_transactions(db, portfolio.id), strict=False)
    warnings = list(ledger.warnings)
    stocks = {st.id: st for st in db.query(Stock).filter(Stock.id.in_(list(ledger.positions) or [-1])).all()}

    rows = []
    tot_mv = tot_cost = tot_day = tot_realized = tot_div = ZERO
    fx_sources: set[str] = set()
    for sid, pos in ledger.positions.items():
        st = stocks[sid]
        tot_realized_local = pos.realized_pl
        tot_div_local = pos.dividends
        rate, src = fx_rate(db, st.currency, base)
        fx_sources.add(src)
        if rate is None:
            warnings.append(f"No FX rate {st.currency}->{base}; {st.ticker} excluded from totals")
        if rate is not None:
            tot_realized += tot_realized_local * rate
            tot_div += tot_div_local * rate
        if pos.quantity == 0:
            continue
        q = st.quote
        price = q.price if q and q.price is not None else None
        mv = pos.quantity * price if price is not None else None
        unreal = mv - pos.cost_basis if mv is not None else None
        unreal_pct = (unreal / pos.cost_basis * 100) if (unreal is not None and pos.cost_basis) else None
        day_pl = pos.quantity * q.change if (q and q.change is not None) else None
        stale = is_stale(q, stale_after, now)
        age = int((now - q.last_success_at).total_seconds()) if q and q.last_success_at else None
        if price is None:
            warnings.append(f"No price for {st.ticker}; valued at cost")
        mv_base = (mv if mv is not None else pos.cost_basis) * rate if rate is not None else None
        if rate is not None:
            tot_mv += mv_base
            tot_cost += pos.cost_basis * rate
            tot_day += (day_pl or ZERO) * rate
        rows.append({
            "stock_id": sid, "ticker": st.ticker, "company": st.company, "currency": st.currency,
            "sector": st.sector or "Unclassified", "market": st.market,
            "quantity": str(pos.quantity.normalize()), "avg_cost": s(pos.avg_cost, 4), "cost_basis": s(pos.cost_basis),
            "price": s(price, 4) if price is not None else None, "market_value": s(mv),
            "market_value_base": s(mv_base), "unrealized_pl": s(unreal), "unrealized_pct": s(unreal_pct),
            "day_change": s(q.change, 4) if q and q.change is not None else None,
            "day_change_pct": s(q.change_pct) if q and q.change_pct is not None else None,
            "day_pl": s(day_pl), "realized_pl": s(pos.realized_pl), "dividends": s(pos.dividends),
            "fees": s(pos.fees), "lots": pos.lots, "market_state": q.market_state if q else "UNKNOWN",
            "quote_age_s": age, "stale": stale, "data_quality": st.data_quality,
            "_mv_base": mv_base, "_pct": q.change_pct if q else None,
        })

    for r in rows:
        r["allocation_pct"] = s(r["_mv_base"] / tot_mv * 100) if (r["_mv_base"] is not None and tot_mv) else None

    def exposure(key: str) -> dict[str, str]:
        agg: dict[str, Decimal] = defaultdict(lambda: ZERO)
        for r in rows:
            if r["_mv_base"] is not None:
                agg[r[key]] += r["_mv_base"]
        return {k: s(v / tot_mv * 100) for k, v in sorted(agg.items(), key=lambda kv: -kv[1])} if tot_mv else {}

    ranked = sorted([r for r in rows if r["_pct"] is not None], key=lambda r: r["_pct"])
    best = {"ticker": ranked[-1]["ticker"], "day_change_pct": ranked[-1]["day_change_pct"]} if ranked else None
    worst = {"ticker": ranked[0]["ticker"], "day_change_pct": ranked[0]["day_change_pct"]} if ranked else None
    ages = [r["quote_age_s"] for r in rows if r["quote_age_s"] is not None]
    cur_exp = exposure("currency")
    sec_exp = exposure("sector")
    for r in rows:
        r.pop("_mv_base")
        r.pop("_pct")

    unreal_tot = tot_mv - tot_cost
    prev_mv = tot_mv - tot_day
    if "peg" in fx_sources:
        warnings.append("Some currency conversions use fixed pegs (no live FX quote).")
    return {
        "portfolio": {"id": portfolio.id, "name": portfolio.name, "base_currency": base},
        "holdings": sorted(rows, key=lambda r: r["ticker"]),
        "totals": {
            "market_value": s(tot_mv), "invested": s(tot_cost), "unrealized_pl": s(unreal_tot),
            "unrealized_pct": s(unreal_tot / tot_cost * 100) if tot_cost else None,
            "day_pl": s(tot_day), "day_pct": s(tot_day / prev_mv * 100) if prev_mv else None,
            "realized_pl": s(tot_realized), "dividends": s(tot_div), "cash": s(ledger.cash),
            "deposits": s(ledger.deposits), "withdrawals": s(ledger.withdrawals),
            "active_holdings": len(rows),
        },
        "exposure": {"currency": cur_exp, "sector": sec_exp},
        "best": best, "worst": worst,
        "freshness": {"oldest_quote_age_s": max(ages) if ages else None,
                      "stale_count": sum(1 for r in rows if r["stale"]), "total": len(rows)},
        "accounting": "average-cost",
        "warnings": warnings,
        "generated_at": now.isoformat(),
    }


def _closes(db: Session, stock_id: int, since: date) -> tuple[list[date], list[Decimal]]:
    hist = (db.query(PriceHistory).filter(PriceHistory.stock_id == stock_id, PriceHistory.day >= since)
            .order_by(PriceHistory.day).all())
    return [h.day for h in hist], [h.close for h in hist]


def value_history(db: Session, portfolio: Portfolio, days: int = 90) -> list[dict]:
    """Daily portfolio value reconstructed from the ledger and stored daily closes."""
    since = date.today() - timedelta(days=days)
    txs = portfolio_transactions(db, portfolio.id)
    if not txs:
        return []
    stock_ids = {t.stock_id for t in txs if t.stock_id}
    series = {sid: _closes(db, sid, since - timedelta(days=10)) for sid in stock_ids}
    rates = {}
    for sid in stock_ids:
        st = db.get(Stock, sid)
        rates[sid] = fx_rate(db, st.currency, portfolio.base_currency)[0]
    all_days = sorted({d for days_, _ in series.values() for d in days_ if d >= since})
    out = []
    for d in all_days:
        pos = compute_positions([t for t in txs if t.trade_date <= d], strict=False).positions
        total = ZERO
        for sid, p in pos.items():
            if p.quantity == 0 or rates.get(sid) is None:
                continue
            ds, cs = series[sid]
            i = bisect_right(ds, d) - 1
            if i >= 0:
                total += p.quantity * cs[i] * rates[sid]
        out.append({"date": d.isoformat(), "value": s(total)})
    return out


def _ret(ds: list[date], cs: list[Decimal], start: date, last: Decimal) -> str | None:
    i = bisect_right(ds, start) - 1
    if i < 0 or not cs[i]:
        return None
    return s((last - cs[i]) / cs[i] * 100)


def benchmarks(db: Session, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    stale_after = settings_store.get(db, "stale_after_s")
    out = []
    today = date.today()
    for b in db.query(Benchmark).filter(Benchmark.active.is_(True)).order_by(Benchmark.sort_order).all():
        q = b.stock.quote
        ds, cs = _closes(db, b.stock_id, today - timedelta(days=400))
        last = q.price if q and q.price is not None else (cs[-1] if cs else None)
        row = {"id": b.id, "name": b.name, "symbol": b.stock.ticker, "level": s(last),
               "day_change_pct": s(q.change_pct) if q and q.change_pct is not None else None,
               "stale": is_stale(q, stale_after, now), "market_state": q.market_state if q else "UNKNOWN",
               "data_quality": b.stock.data_quality}
        if last is not None and ds:
            row.update({"ret_1m": _ret(ds, cs, today - timedelta(days=30), last),
                        "ret_3m": _ret(ds, cs, today - timedelta(days=91), last),
                        "ret_ytd": _ret(ds, cs, date(today.year, 1, 1) - timedelta(days=1), last),
                        "ret_1y": _ret(ds, cs, today - timedelta(days=365), last)})
        out.append(row)
    return out
