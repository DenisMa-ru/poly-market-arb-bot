from __future__ import annotations

from dataclasses import dataclass

from src.clients.base import Orderbook


@dataclass(frozen=True)
class BookFill:
    contracts: float
    avg_price: float
    spent_usd: float


def walk_asks(orderbook: Orderbook, *, max_notional_usd: float, max_price: float = 1.0) -> BookFill:
    taken = 0.0
    spent = 0.0
    for level in orderbook.asks:
        if level.price > max_price:
            break
        remaining_usd = max_notional_usd - spent
        if remaining_usd <= 0:
            break
        max_take = min(level.size, remaining_usd / level.price)
        if max_take <= 0:
            break
        taken += max_take
        spent += max_take * level.price
    return BookFill(contracts=taken, avg_price=(spent / taken) if taken > 0 else 0.0, spent_usd=spent)

