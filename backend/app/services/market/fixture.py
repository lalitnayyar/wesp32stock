"""Deterministic offline provider for tests, demos and fixture mode. Clearly not real market data."""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from .base import MarketDataProvider, ProviderError, QuoteData, SymbolInfo, SymbolNotFound

FIXTURE_SYMBOLS: dict[str, dict] = {
    "AAPL": {"company": "Apple Inc. (fixture)", "exchange": "NASDAQ", "currency": "USD", "sector": "Technology", "price": "189.20", "prev": "187.95"},
    "MSFT": {"company": "Microsoft Corp. (fixture)", "exchange": "NASDAQ", "currency": "USD", "sector": "Technology", "price": "415.10", "prev": "417.40"},
    "NVDA": {"company": "NVIDIA Corp. (fixture)", "exchange": "NASDAQ", "currency": "USD", "sector": "Technology", "price": "121.44", "prev": "117.60"},
    "TSLA": {"company": "Tesla Inc. (fixture)", "exchange": "NASDAQ", "currency": "USD", "sector": "Consumer Cyclical", "price": "238.77", "prev": "243.90"},
    "KO": {"company": "Coca-Cola Co. (fixture)", "exchange": "NYSE", "currency": "USD", "sector": "Consumer Defensive", "price": "63.10", "prev": "63.10"},
    "EMAAR.AE": {"company": "Emaar Properties (fixture)", "exchange": "DFM", "currency": "AED", "sector": "Real Estate", "price": "8.42", "prev": "8.31"},
    "DIB.AE": {"company": "Dubai Islamic Bank (fixture)", "exchange": "DFM", "currency": "AED", "sector": "Financial Services", "price": "6.05", "prev": "6.11"},
    "^GSPC": {"company": "S&P 500 (fixture)", "exchange": "SNP", "currency": "USD", "kind": "index", "price": "5712.30", "prev": "5688.90"},
    "^IXIC": {"company": "NASDAQ Composite (fixture)", "exchange": "NIM", "currency": "USD", "kind": "index", "price": "18210.55", "prev": "18110.20"},
    "USDAED=X": {"company": "USD/AED (fixture)", "exchange": "CCY", "currency": "AED", "kind": "fx", "price": "3.6725", "prev": "3.6725"},
    "AEDUSD=X": {"company": "AED/USD (fixture)", "exchange": "CCY", "currency": "USD", "kind": "fx", "price": "0.27229", "prev": "0.27229"},
}

FAIL_SYMBOLS = {"FAIL.TEST"}


class FixtureProvider(MarketDataProvider):
    name = "fixture"

    def get_quote(self, symbol: str) -> QuoteData:
        if symbol in FAIL_SYMBOLS:
            raise ProviderError(f"{symbol}: simulated provider outage")
        spec = FIXTURE_SYMBOLS.get(symbol)
        if spec is None:
            raise SymbolNotFound(f"{symbol}: not available in fixture provider")
        return QuoteData(symbol=symbol, price=Decimal(spec["price"]), prev_close=Decimal(spec["prev"]),
                         currency=spec["currency"], quote_time=datetime.now(timezone.utc), delayed=True)

    def validate_symbol(self, symbol: str) -> SymbolInfo:
        spec = FIXTURE_SYMBOLS.get(symbol)
        if spec is None:
            raise SymbolNotFound(f"{symbol}: not available in fixture provider")
        return SymbolInfo(symbol=symbol, company=spec["company"], exchange=spec["exchange"],
                          currency=spec["currency"], sector=spec.get("sector", ""), kind=spec.get("kind", "equity"))

    def get_history(self, symbol: str, days: int) -> list[tuple[date, Decimal]]:
        spec = FIXTURE_SYMBOLS.get(symbol)
        if spec is None:
            raise SymbolNotFound(symbol)
        price = Decimal(spec["price"])
        seed = int(hashlib.sha256(symbol.encode()).hexdigest()[:8], 16)
        out = []
        today = date.today()
        for i in range(days, 0, -1):
            wiggle = Decimal(((seed >> (i % 24)) % 21) - 10) / Decimal(1000)
            trend = Decimal(i) / Decimal(days * 10)
            out.append((today - timedelta(days=i), (price * (1 - trend + wiggle)).quantize(Decimal("0.0001"))))
        return out
