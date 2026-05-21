from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class Venue(str, Enum):
    POLYMARKET = "polymarket"


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class Outcome(str, Enum):
    YES = "YES"
    NO = "NO"


@dataclass(frozen=True)
class OrderbookLevel:
    price: float
    size: float


@dataclass(frozen=True)
class Orderbook:
    venue: Venue
    market_id: str
    outcome: Outcome
    bids: tuple[OrderbookLevel, ...]
    asks: tuple[OrderbookLevel, ...]
    fetched_at_ms: int

    @property
    def best_ask(self) -> OrderbookLevel | None:
        return self.asks[0] if self.asks else None


@dataclass(frozen=True)
class Market:
    venue: Venue
    market_id: str
    question: str
    outcomes: tuple[str, ...]
    yes_token_id: str | None = None
    no_token_id: str | None = None
    closes_at_iso: str | None = None
    category: str | None = None
    raw: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class OrderRequest:
    venue: Venue
    market_id: str
    outcome: Outcome
    side: Side
    size: float
    price: float
    client_id: str | None = None


@dataclass(frozen=True)
class OrderResult:
    venue: Venue
    venue_order_id: str | None
    accepted: bool
    filled_size: float
    avg_fill_price: float
    fee_usd: float
    raw_response: dict[str, object]
    error: str | None = None


class BaseExchangeClient(ABC):
    venue: Venue

    @abstractmethod
    async def list_markets(self, *, active_only: bool = True) -> list[Market]: ...

    @abstractmethod
    async def get_orderbook(self, market_id: str, outcome: Outcome) -> Orderbook: ...

    @abstractmethod
    async def get_balance_usd(self) -> float: ...

    @abstractmethod
    async def place_order(self, req: OrderRequest) -> OrderResult: ...

    @abstractmethod
    async def cancel_order(self, venue_order_id: str) -> bool: ...

    @abstractmethod
    async def close(self) -> None: ...

