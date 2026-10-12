"""Replaceable market-data provider interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


class ProviderError(Exception):
    """Base provider error. `retryable` drives retry/backoff."""

    retryable = True
    code = "provider_error"


class RateLimited(ProviderError):
    code = "rate_limited"


class SymbolNotFound(ProviderError):
    retryable = False
    code = "symbol_not_found"


@dataclass
class QuoteData:
    symbol: str
    price: Decimal
    prev_close: Decimal | None
    currency: str
    quote_time: datetime | None
    market_state: str | None = None  # provider-reported, if any
    delayed: bool = True


@dataclass
class SymbolInfo:
    symbol: str
    company: str
    exchange: str
    currency: str
    sector: str = ""
    industry: str = ""
    country: str = ""
    kind: str = "equity"


class MarketDataProvider(ABC):
    name = "abstract"

    @abstractmethod
    def get_quote(self, symbol: str) -> QuoteData:
        """Fetch one quote (blocking). Raise ProviderError subclasses on failure."""

    @abstractmethod
    def validate_symbol(self, symbol: str) -> SymbolInfo:
        """Return metadata for a supported symbol or raise SymbolNotFound."""

    @abstractmethod
    def get_history(self, symbol: str, days: int) -> list[tuple[date, Decimal]]:
        """Daily closes, oldest first."""
