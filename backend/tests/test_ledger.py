from dataclasses import dataclass
from datetime import date
from decimal import Decimal as D

import pytest

from app.services.ledger import LedgerError, compute_positions


@dataclass
class Tx:
    id: int
    type: str
    trade_date: date
    stock_id: int | None = 1
    quantity: D = D(0)
    price: D = D(0)
    fees: D = D(0)
    amount: D = D(0)
    split_ratio: D | None = None
    notes: str = ""


def d(n):
    return date(2026, 1, n)


def test_average_cost_multiple_buys_with_fees():
    res = compute_positions([
        Tx(1, "BUY", d(1), quantity=D("10"), price=D("100.10"), fees=D("1.00")),
        Tx(2, "BUY", d(2), quantity=D("5"), price=D("110.30"), fees=D("0.50")),
    ])
    p = res.positions[1]
    assert p.quantity == D("15")
    assert p.cost_basis == D("1002.00") + D("552.00")   # fees are part of cost basis
    assert p.avg_cost == D("1554.00") / D("15")
    assert res.cash == -D("1554.00")


def test_sell_realizes_against_average_cost():
    res = compute_positions([
        Tx(1, "BUY", d(1), quantity=D("10"), price=D("100"), fees=D("0")),
        Tx(2, "BUY", d(2), quantity=D("10"), price=D("120"), fees=D("0")),
        Tx(3, "SELL", d(3), quantity=D("5"), price=D("130"), fees=D("2")),
    ])
    p = res.positions[1]
    assert p.quantity == D("15")
    assert p.cost_basis == D("1650")           # 2200 - 5 * 110
    assert p.realized_pl == D("650") - D("2") - D("550")
    assert p.avg_cost == D("110")


def test_sell_everything_zeroes_cost():
    res = compute_positions([
        Tx(1, "BUY", d(1), quantity=D("3"), price=D("10")),
        Tx(2, "SELL", d(2), quantity=D("3"), price=D("12")),
    ])
    assert res.positions[1].quantity == 0 and res.positions[1].cost_basis == 0
    assert res.positions[1].realized_pl == D("6")


def test_oversell_rejected_in_strict_mode_and_warned_otherwise():
    txs = [Tx(1, "BUY", d(1), quantity=D("1"), price=D("10")), Tx(2, "SELL", d(2), quantity=D("2"), price=D("10"))]
    with pytest.raises(LedgerError):
        compute_positions(txs)
    res = compute_positions(txs, strict=False)
    assert res.warnings and res.positions[1].quantity == 0


def test_split_keeps_cost_and_halves_average():
    res = compute_positions([
        Tx(1, "BUY", d(1), quantity=D("10"), price=D("200")),
        Tx(2, "SPLIT", d(2), split_ratio=D("2")),
    ])
    p = res.positions[1]
    assert p.quantity == D("20") and p.cost_basis == D("2000") and p.avg_cost == D("100")


def test_dividends_and_fees_and_cash():
    res = compute_positions([
        Tx(1, "DEPOSIT", d(1), stock_id=None, amount=D("5000")),
        Tx(2, "BUY", d(2), quantity=D("10"), price=D("100"), fees=D("1")),
        Tx(3, "DIVIDEND", d(3), amount=D("12.50"), fees=D("0.50")),
        Tx(4, "FEE", d(4), stock_id=None, amount=D("3")),
        Tx(5, "WITHDRAWAL", d(5), stock_id=None, amount=D("100")),
    ])
    assert res.positions[1].dividends == D("12.00")
    assert res.portfolio_fees == D("3")
    assert res.cash == D("5000") - D("1001") + D("12.00") - D("3") - D("100")


def test_adjustment_requires_reason():
    with pytest.raises(LedgerError):
        compute_positions([Tx(1, "BUY", d(1), quantity=D("1"), price=D("1")),
                           Tx(2, "ADJUSTMENT", d(2), quantity=D("1"))])
    res = compute_positions([Tx(1, "BUY", d(1), quantity=D("1"), price=D("1")),
                             Tx(2, "ADJUSTMENT", d(2), quantity=D("1"), amount=D("1"), notes="broker correction")])
    assert res.positions[1].quantity == D("2") and res.positions[1].cost_basis == D("2")


def test_decimal_exactness():
    res = compute_positions([Tx(i, "BUY", d(1), quantity=D("0.1"), price=D("0.2")) for i in range(1, 11)])
    assert res.positions[1].cost_basis == D("0.20")  # exact; float would give 0.20000000000000004


def test_date_order_not_insert_order():
    res = compute_positions([
        Tx(2, "SELL", d(5), quantity=D("1"), price=D("10")),
        Tx(1, "BUY", d(1), quantity=D("1"), price=D("5")),
    ])
    assert res.positions[1].realized_pl == D("5")
