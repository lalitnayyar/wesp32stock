from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.security import current_admin
from ..models import TX_TYPES, Broker, Device, Portfolio, Stock, Transaction, User
from ..services import analytics
from ..services.audit import audit
from ..services.ledger import LedgerError, compute_positions
from .common import get_or_404

router = APIRouter(prefix="/api/v1", tags=["portfolios"])


# ----------------------------------------------------------------------------- brokers

class BrokerIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    account_ref: str = ""
    notes: str = ""


@router.get("/brokers")
def list_brokers(db: Session = Depends(get_db), _: User = Depends(current_admin)):
    return [{"id": b.id, "name": b.name, "account_ref": b.account_ref, "notes": b.notes}
            for b in db.query(Broker).order_by(Broker.name).all()]


@router.post("/brokers", status_code=201)
def create_broker(body: BrokerIn, db: Session = Depends(get_db), user: User = Depends(current_admin)):
    b = Broker(**body.model_dump())
    db.add(b)
    db.commit()
    audit(db, user.username, "broker_created", "broker", b.id, body.model_dump())
    return {"id": b.id, **body.model_dump()}


@router.put("/brokers/{bid}")
def update_broker(bid: int, body: BrokerIn, db: Session = Depends(get_db), user: User = Depends(current_admin)):
    b = get_or_404(db, Broker, bid, "Broker")
    for k, v in body.model_dump().items():
        setattr(b, k, v)
    db.commit()
    audit(db, user.username, "broker_updated", "broker", bid, body.model_dump())
    return {"id": b.id, **body.model_dump()}


@router.delete("/brokers/{bid}")
def delete_broker(bid: int, db: Session = Depends(get_db), user: User = Depends(current_admin)):
    b = get_or_404(db, Broker, bid, "Broker")
    db.delete(b)
    db.commit()
    audit(db, user.username, "broker_deleted", "broker", bid)
    return {"ok": True}


# ----------------------------------------------------------------------------- portfolios

class PortfolioIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    base_currency: str = Field("USD", min_length=3, max_length=3)
    broker_id: int | None = None
    description: str = ""
    active: bool = True


def pf_out(p: Portfolio) -> dict:
    return {"id": p.id, "name": p.name, "base_currency": p.base_currency, "broker_id": p.broker_id,
            "description": p.description, "active": p.active, "created_at": p.created_at}


@router.get("/portfolios")
def list_portfolios(db: Session = Depends(get_db), _: User = Depends(current_admin)):
    return [pf_out(p) for p in db.query(Portfolio).order_by(Portfolio.name).all()]


@router.post("/portfolios", status_code=201)
def create_portfolio(body: PortfolioIn, db: Session = Depends(get_db), user: User = Depends(current_admin)):
    p = Portfolio(**{**body.model_dump(), "base_currency": body.base_currency.upper()})
    db.add(p)
    db.commit()
    audit(db, user.username, "portfolio_created", "portfolio", p.id, body.model_dump())
    return pf_out(p)


@router.get("/portfolios/{pid}")
def get_portfolio(pid: int, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    return pf_out(get_or_404(db, Portfolio, pid, "Portfolio"))


@router.put("/portfolios/{pid}")
def update_portfolio(pid: int, body: PortfolioIn, db: Session = Depends(get_db), user: User = Depends(current_admin)):
    p = get_or_404(db, Portfolio, pid, "Portfolio")
    for k, v in body.model_dump().items():
        setattr(p, k, v.upper() if k == "base_currency" else v)
    db.commit()
    audit(db, user.username, "portfolio_updated", "portfolio", pid, body.model_dump())
    return pf_out(p)


@router.delete("/portfolios/{pid}")
def delete_portfolio(pid: int, body: dict | None = None, db: Session = Depends(get_db),
                     user: User = Depends(current_admin)):
    p = get_or_404(db, Portfolio, pid, "Portfolio")
    n = db.query(Transaction).filter(Transaction.portfolio_id == pid).count()
    if n and not (body or {}).get("confirm"):
        raise HTTPException(409, f"Portfolio has {n} transactions; send {{\"confirm\": true}} to delete them too")
    db.query(Transaction).filter(Transaction.portfolio_id == pid).delete()
    db.query(Device).filter(Device.portfolio_id == pid).update({Device.portfolio_id: None})
    db.delete(p)
    db.commit()
    audit(db, user.username, "portfolio_deleted", "portfolio", pid, {"transactions": n})
    return {"ok": True}


@router.get("/portfolios/{pid}/summary")
def portfolio_summary(pid: int, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    return analytics.portfolio_summary(db, get_or_404(db, Portfolio, pid, "Portfolio"))


@router.get("/portfolios/{pid}/history")
def portfolio_history(pid: int, days: int = 90, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    return analytics.value_history(db, get_or_404(db, Portfolio, pid, "Portfolio"), min(max(days, 7), 730))


# ----------------------------------------------------------------------------- transactions

class TransactionIn(BaseModel):
    type: str
    stock_id: int | None = None
    broker_id: int | None = None
    trade_date: date
    quantity: Decimal = Decimal(0)
    price: Decimal = Decimal(0)
    fees: Decimal = Decimal(0)
    amount: Decimal = Decimal(0)
    split_ratio: Decimal | None = None
    currency: str | None = None
    notes: str = ""

    @field_validator("type")
    @classmethod
    def _type(cls, v: str) -> str:
        v = v.upper()
        if v not in TX_TYPES:
            raise ValueError(f"type must be one of {', '.join(TX_TYPES)}")
        return v

    @field_validator("quantity", "price", "fees", "amount")
    @classmethod
    def _finite(cls, v: Decimal) -> Decimal:
        if not v.is_finite() or abs(v) > Decimal("1e15"):
            raise ValueError("must be a finite number")
        return v


def tx_out(t: Transaction, tickers: dict[int, str] | None = None) -> dict:
    return {"id": t.id, "portfolio_id": t.portfolio_id, "stock_id": t.stock_id,
            "ticker": (tickers or {}).get(t.stock_id) if t.stock_id else None, "broker_id": t.broker_id,
            "type": t.type, "trade_date": t.trade_date.isoformat(), "quantity": analytics.plain(t.quantity),
            "price": analytics.plain(t.price), "fees": analytics.plain(t.fees), "amount": analytics.plain(t.amount),
            "split_ratio": analytics.plain(t.split_ratio) if t.split_ratio is not None else None,
            "currency": t.currency, "notes": t.notes, "created_by": t.created_by, "created_at": t.created_at}


def _check_ledger(db: Session, pid: int, candidate: list[Transaction]) -> None:
    try:
        compute_positions(candidate, strict=True)
    except LedgerError as exc:
        db.rollback()
        raise HTTPException(422, str(exc))


@router.get("/portfolios/{pid}/transactions")
def list_transactions(pid: int, db: Session = Depends(get_db), _: User = Depends(current_admin)):
    get_or_404(db, Portfolio, pid, "Portfolio")
    txs = (db.query(Transaction).filter(Transaction.portfolio_id == pid)
           .order_by(Transaction.trade_date.desc(), Transaction.id.desc()).all())
    tickers = {s.id: s.ticker for s in db.query(Stock).all()}
    return [tx_out(t, tickers) for t in txs]


def _apply(t: Transaction, body: TransactionIn, db: Session) -> None:
    if body.stock_id is not None:
        st = get_or_404(db, Stock, body.stock_id, "Stock")
        default_ccy = st.currency
    else:
        default_ccy = None
    if body.type in ("BUY", "SELL", "DIVIDEND", "SPLIT", "ADJUSTMENT") and body.stock_id is None:
        raise HTTPException(422, f"{body.type} requires stock_id")
    if body.type in ("DEPOSIT", "WITHDRAWAL") and body.stock_id is not None:
        raise HTTPException(422, f"{body.type} must not reference a stock")
    if body.type == "SPLIT" and (body.split_ratio is None or body.split_ratio <= 0):
        raise HTTPException(422, "SPLIT requires split_ratio > 0 (e.g. 2 for a 2-for-1 split)")
    if body.type == "ADJUSTMENT" and not body.notes.strip():
        raise HTTPException(422, "ADJUSTMENT requires a reason in notes (audited)")
    for k, v in body.model_dump().items():
        setattr(t, k, v)
    t.currency = (body.currency or default_ccy or "USD").upper()


@router.post("/portfolios/{pid}/transactions", status_code=201)
def create_transaction(pid: int, body: TransactionIn, db: Session = Depends(get_db), user: User = Depends(current_admin)):
    get_or_404(db, Portfolio, pid, "Portfolio")
    t = Transaction(portfolio_id=pid, created_by=user.username)
    _apply(t, body, db)
    db.add(t)
    db.flush()
    _check_ledger(db, pid, db.query(Transaction).filter(Transaction.portfolio_id == pid).all())
    db.commit()
    audit(db, user.username, "transaction_created", "transaction", t.id, body.model_dump(mode="json"))
    return tx_out(t)


@router.put("/transactions/{tid}")
def update_transaction(tid: int, body: TransactionIn, db: Session = Depends(get_db), user: User = Depends(current_admin)):
    t = get_or_404(db, Transaction, tid, "Transaction")
    before = tx_out(t)
    _apply(t, body, db)
    db.flush()
    _check_ledger(db, t.portfolio_id, db.query(Transaction).filter(Transaction.portfolio_id == t.portfolio_id).all())
    db.commit()
    audit(db, user.username, "transaction_updated", "transaction", tid,
          {"before": before, "after": body.model_dump(mode="json")})
    return tx_out(t)


@router.delete("/transactions/{tid}")
def delete_transaction(tid: int, db: Session = Depends(get_db), user: User = Depends(current_admin)):
    t = get_or_404(db, Transaction, tid, "Transaction")
    before = tx_out(t)
    pid = t.portfolio_id
    db.delete(t)
    db.flush()
    _check_ledger(db, pid, db.query(Transaction).filter(Transaction.portfolio_id == pid).all())
    db.commit()
    audit(db, user.username, "transaction_deleted", "transaction", tid, before)
    return {"ok": True}


@router.get("/analytics/overview")
def overview(db: Session = Depends(get_db), _: User = Depends(current_admin)):
    out = []
    for p in db.query(Portfolio).filter(Portfolio.active.is_(True)).order_by(Portfolio.name).all():
        s = analytics.portfolio_summary(db, p)
        out.append({"portfolio": s["portfolio"], "totals": s["totals"], "freshness": s["freshness"],
                    "best": s["best"], "worst": s["worst"], "warnings": s["warnings"]})
    return {"portfolios": out, "benchmarks": analytics.benchmarks(db)}
