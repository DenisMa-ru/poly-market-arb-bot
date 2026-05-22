from __future__ import annotations

from dataclasses import dataclass

from src.clients.base import Orderbook
from src.markets.updown_parser import UpDownMarket


@dataclass(frozen=True)
class PreOrderConfig:
    enabled: bool
    target_price_up: float
    target_price_down: float
    max_bundle_cost: float


@dataclass(frozen=True)
class PreOrderResult:
    slug: str
    symbol: str
    timeframe_minutes: int
    target_price_up: float
    target_price_down: float
    filled_up: bool
    filled_down: bool
    cost_up: float | None
    cost_down: float | None
    bundle_cost: float | None
    status: str
    expected_pnl: float | None


class PreOrderSimulator:
    def __init__(self, config: PreOrderConfig) -> None:
        self.config = config

    def evaluate(self, market: UpDownMarket, up_book: Orderbook, down_book: Orderbook) -> PreOrderResult:
        up_ask = up_book.best_ask.price if up_book.best_ask else None
        down_ask = down_book.best_ask.price if down_book.best_ask else None

        filled_up = up_ask is not None and up_ask <= self.config.target_price_up
        filled_down = down_ask is not None and down_ask <= self.config.target_price_down

        cost_up = self.config.target_price_up if filled_up else None
        cost_down = self.config.target_price_down if filled_down else None

        if filled_up and filled_down:
            bundle_cost = self.config.target_price_up + self.config.target_price_down
            expected_pnl = 1.0 - bundle_cost
            status = "full_fill" if bundle_cost <= self.config.max_bundle_cost else "full_fill_over_budget"
        elif filled_up or filled_down:
            bundle_cost = None
            expected_pnl = None
            status = "partial_fill"
        else:
            bundle_cost = None
            expected_pnl = None
            status = "no_fill"

        return PreOrderResult(
            slug=market.slug,
            symbol=market.symbol,
            timeframe_minutes=market.timeframe_minutes,
            target_price_up=self.config.target_price_up,
            target_price_down=self.config.target_price_down,
            filled_up=filled_up,
            filled_down=filled_down,
            cost_up=cost_up,
            cost_down=cost_down,
            bundle_cost=bundle_cost,
            status=status,
            expected_pnl=expected_pnl,
        )
