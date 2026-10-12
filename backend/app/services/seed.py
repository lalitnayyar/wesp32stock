"""Bootstrap (admin user, default benchmarks) and optional demo data."""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.crypto import hash_password
from ..models import (
    ApiKey, Benchmark, Broker, Device, Portfolio, PriceHistory, Quote, Stock, Transaction, User,
)
from . import settings_store
from .market.hours import market_for_symbol

log = logging.getLogger(__name__)

# Benchmarks: symbols must be supported by the provider. DFMGI.AE and FADGI.FGI returned data from
# Yahoo on 2026-10-12, but they are created inactive so the administrator validates them
# ("Validate & activate") against the live provider before use.
DEFAULT_BENCHMARKS = [
    ("S&P 500", "^GSPC", "US", True, "Yahoo index symbol"),
    ("NASDAQ Comp", "^IXIC", "US", True, "Yahoo index symbol"),
    ("DFM General", "DFMGI.AE", "DFM", False, "Validate & activate before use"),
    ("FTSE ADX Gen", "FADGI.FGI", "ADX", False, "Validate & activate before use"),
]

FX_SYMBOLS = [("USDAED=X", "USD/AED", "AED")]

MIN_ADMIN_PASSWORD = 12


def bootstrap(db: Session) -> None:
    s = get_settings()
    if db.query(User).count() == 0:
        if not s.admin_password:
            log.warning("No admin user exists and ADMIN_PASSWORD is not set; set it and restart to create one")
        elif len(s.admin_password) < MIN_ADMIN_PASSWORD:
            log.error("ADMIN_PASSWORD must be at least %s characters; admin not created", MIN_ADMIN_PASSWORD)
        else:
            db.add(User(username=s.admin_username, password_hash=hash_password(s.admin_password)))
            log.info("created initial admin user %s", s.admin_username)
    for i, (name, sym, mkt, active, note) in enumerate(DEFAULT_BENCHMARKS):
        st = db.query(Stock).filter(Stock.ticker == sym).one_or_none()
        if st is None:
            st = Stock(ticker=sym, company=name, kind="index", market=mkt, currency="USD" if sym.startswith("^") else "AED",
                       provider=s.market_provider, active=active, notes=note,
                       data_quality="unvalidated")
            db.add(st)
            db.flush()
            db.add(Benchmark(name=name, stock_id=st.id, active=active, sort_order=i))
        elif st.kind == "index" and st.market in ("", "INDEX"):
            st.market = mkt
    for sym, name, ccy in FX_SYMBOLS:
        if db.query(Stock).filter(Stock.ticker == sym).one_or_none() is None:
            db.add(Stock(ticker=sym, company=name, kind="fx", market="FX", currency=ccy, provider=s.market_provider))
    db.commit()


DEMO_STOCKS = [
    ("AAPL", "Apple Inc.", "NASDAQ", "USD", "Technology"),
    ("MSFT", "Microsoft Corp.", "NASDAQ", "USD", "Technology"),
    ("NVDA", "NVIDIA Corp.", "NASDAQ", "USD", "Technology"),
    ("TSLA", "Tesla Inc.", "NASDAQ", "USD", "Consumer Cyclical"),
    ("KO", "Coca-Cola Co.", "NYSE", "USD", "Consumer Defensive"),
    ("EMAAR.AE", "Emaar Properties", "DFM", "AED", "Real Estate"),
    ("DIB.AE", "Dubai Islamic Bank", "DFM", "AED", "Financial Services"),
]

DEMO_TAG = "[demo]"


def seed_demo(db: Session) -> dict:
    if settings_store.get(db, "demo_data_loaded"):
        return {"created": False, "message": "Demo data already loaded"}
    broker = Broker(name=f"Demo Broker {DEMO_TAG}", account_ref="DEMO-001", notes=DEMO_TAG)
    db.add(broker)
    db.flush()
    pf = Portfolio(name="Demo Portfolio", base_currency="USD", broker_id=broker.id, description=DEMO_TAG)
    db.add(pf)
    db.flush()
    stock_ids = {}
    for sym, company, exch, ccy, sector in DEMO_STOCKS:
        st = db.query(Stock).filter(Stock.ticker == sym).one_or_none()
        if st is None:
            st = Stock(ticker=sym, company=company, exchange=exch, currency=ccy, sector=sector,
                       market=market_for_symbol(sym), notes=DEMO_TAG, provider=get_settings().market_provider)
            db.add(st)
            db.flush()
        stock_ids[sym] = st.id
    d0 = date.today() - timedelta(days=200)
    txs = [
        ("DEPOSIT", None, 0, 0, 0, "60000"),
        ("BUY", "AAPL", 50, "150.10", "1.00", 0),
        ("BUY", "AAPL", 25, "172.40", "1.00", 0),
        ("BUY", "MSFT", 20, "380.00", "1.00", 0),
        ("BUY", "NVDA", 100, "95.20", "1.00", 0),
        ("SELL", "NVDA", 20, "118.00", "1.00", 0),
        ("BUY", "TSLA", 15, "250.00", "1.00", 0),
        ("BUY", "KO", 60, "58.30", "1.00", 0),
        ("DIVIDEND", "KO", 0, 0, 0, "29.10"),
        ("BUY", "EMAAR.AE", 1500, "7.95", "15.00", 0),
        ("BUY", "DIB.AE", 1200, "5.80", "12.00", 0),
    ]
    for i, (typ, sym, q, p, fee, amt) in enumerate(txs):
        st_id = stock_ids.get(sym) if sym else None
        ccy = "AED" if sym and sym.endswith(".AE") else "USD"
        db.add(Transaction(portfolio_id=pf.id, stock_id=st_id, type=typ, trade_date=d0 + timedelta(days=i * 12),
                           quantity=Decimal(str(q)), price=Decimal(str(p)), fees=Decimal(str(fee)),
                           amount=Decimal(str(amt)), currency=ccy, notes=DEMO_TAG, created_by="demo"))
    db.commit()
    settings_store.set_many(db, {"demo_data_loaded": True})
    return {"created": True, "portfolio_id": pf.id}


def remove_demo(db: Session) -> dict:
    pfs = db.query(Portfolio).filter(Portfolio.description == DEMO_TAG).all()
    for pf in pfs:
        db.query(Transaction).filter(Transaction.portfolio_id == pf.id).delete()
        db.query(Device).filter(Device.portfolio_id == pf.id).update({Device.portfolio_id: None})
        db.delete(pf)
    db.flush()
    removed_stocks = 0
    for st in db.query(Stock).filter(Stock.notes == DEMO_TAG).all():
        if db.query(Transaction).filter(Transaction.stock_id == st.id).count() == 0:
            db.query(PriceHistory).filter(PriceHistory.stock_id == st.id).delete()
            db.query(Quote).filter(Quote.stock_id == st.id).delete()
            db.delete(st)
            removed_stocks += 1
    db.query(Broker).filter(Broker.notes == DEMO_TAG).delete()
    db.commit()
    settings_store.set_many(db, {"demo_data_loaded": False})
    return {"portfolios": len(pfs), "stocks": removed_stocks}


def reset_application_data(db: Session) -> None:
    """Remove all portfolio/market/device data. Users and settings are kept."""
    for model in (Transaction, ApiKey, Device, Portfolio, Broker, PriceHistory, Quote, Benchmark, Stock):
        db.query(model).delete()
    db.commit()
    settings_store.set_many(db, {"demo_data_loaded": False})
    bootstrap(db)
