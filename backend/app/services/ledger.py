"""Transaction ledger -> holdings, using average-cost accounting.

Average cost: each BUY adds quantity and (quantity * price + fees) to the cost basis. A SELL
removes the proportional average cost; realized P/L = proceeds - fees - removed cost. SPLIT
multiplies quantity by the ratio and leaves cost unchanged. ADJUSTMENT applies a signed
quantity delta and a signed cost delta (amount) and must carry a reason in notes.

FIFO is a planned alternative: holdings would keep a lot list instead of (qty, cost). The
public API (compute_positions) is lot-agnostic so the method can be swapped later.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal

ZERO = Decimal(0)


class LedgerError(ValueError):
    pass


@dataclass
class Position:
    stock_id: int
    quantity: Decimal = ZERO
    cost_basis: Decimal = ZERO
    realized_pl: Decimal = ZERO
    dividends: Decimal = ZERO
    fees: Decimal = ZERO
    first_buy: object | None = None
    lots: int = 0

    @property
    def avg_cost(self) -> Decimal:
        return (self.cost_basis / self.quantity) if self.quantity else ZERO


@dataclass
class LedgerResult:
    positions: dict[int, Position] = field(default_factory=dict)
    cash: Decimal = ZERO
    deposits: Decimal = ZERO
    withdrawals: Decimal = ZERO
    portfolio_fees: Decimal = ZERO
    warnings: list[str] = field(default_factory=list)


def _d(v) -> Decimal:
    if v is None:
        return ZERO
    return v if isinstance(v, Decimal) else Decimal(str(v))


def compute_positions(transactions: Iterable, strict: bool = True) -> LedgerResult:
    """Replay transactions (objects with type, stock_id, quantity, price, fees, amount,
    split_ratio, trade_date, id) in date order."""
    res = LedgerResult()
    txs = sorted(transactions, key=lambda t: (t.trade_date, t.id or 0))
    for t in txs:
        q, p, fee, amt = _d(t.quantity), _d(t.price), _d(t.fees), _d(t.amount)
        typ = t.type
        if typ in ("BUY", "SELL", "DIVIDEND", "SPLIT", "ADJUSTMENT") and t.stock_id is None:
            raise LedgerError(f"{typ} transaction {t.id} requires a stock")
        pos = res.positions.setdefault(t.stock_id, Position(t.stock_id)) if t.stock_id is not None else None
        if typ == "BUY":
            if q <= 0 or p < 0 or fee < 0:
                raise LedgerError(f"BUY {t.id}: quantity must be > 0 and price/fees >= 0")
            pos.quantity += q
            pos.cost_basis += q * p + fee
            pos.fees += fee
            pos.lots += 1
            pos.first_buy = pos.first_buy or t.trade_date
            res.cash -= q * p + fee
        elif typ == "SELL":
            if q <= 0 or p < 0 or fee < 0:
                raise LedgerError(f"SELL {t.id}: quantity must be > 0 and price/fees >= 0")
            if q > pos.quantity:
                msg = f"SELL {t.id}: quantity {q} exceeds holding {pos.quantity}"
                if strict:
                    raise LedgerError(msg)
                res.warnings.append(msg)
                q = pos.quantity
            removed = pos.avg_cost * q
            pos.realized_pl += q * p - fee - removed
            pos.cost_basis -= removed
            pos.quantity -= q
            pos.fees += fee
            if pos.quantity == 0:
                pos.cost_basis = ZERO
            res.cash += q * p - fee
        elif typ == "DIVIDEND":
            pos.dividends += amt - fee
            pos.fees += fee
            res.cash += amt - fee
        elif typ == "SPLIT":
            ratio = _d(t.split_ratio)
            if ratio <= 0:
                raise LedgerError(f"SPLIT {t.id}: ratio must be > 0")
            pos.quantity *= ratio
        elif typ == "FEE":
            if pos is not None:
                pos.fees += amt
                pos.realized_pl -= amt
            else:
                res.portfolio_fees += amt
            res.cash -= amt
        elif typ == "DEPOSIT":
            res.deposits += amt
            res.cash += amt
        elif typ == "WITHDRAWAL":
            res.withdrawals += amt
            res.cash -= amt
        elif typ == "ADJUSTMENT":
            if not (t.notes or "").strip():
                raise LedgerError(f"ADJUSTMENT {t.id}: a reason is required in notes")
            pos.quantity += q
            pos.cost_basis += amt
            if pos.quantity < 0:
                raise LedgerError(f"ADJUSTMENT {t.id}: resulting quantity is negative")
        else:
            raise LedgerError(f"Unknown transaction type {typ}")
    return res
