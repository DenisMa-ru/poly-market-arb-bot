from __future__ import annotations

from dataclasses import dataclass

from src.clients.base import Orderbook
from src.markets.updown_parser import UpDownMarket


@dataclass(frozen=True)
class PairMarketMakerConfig:
    enabled: bool
    markets_limit: int
    target_pairs: float
    quote_edge: float
    skew_step: float
    max_skew: float
    reward_per_trade_usd: float


@dataclass
class PairMarketMakerState:
    up_inventory: float = 0.0
    down_inventory: float = 0.0
    realized_pnl: float = 0.0
    reward_pnl: float = 0.0
    completed_pairs: float = 0.0


class PairMarketMaker:
    def __init__(self, config: PairMarketMakerConfig) -> None:
        self.config = config

    def evaluate(self, market: UpDownMarket, up_book: Orderbook, down_book: Orderbook, state: PairMarketMakerState) -> dict[str, object]:
        up_bid = up_book.bids[0].price if up_book.bids else None
        up_ask = up_book.asks[0].price if up_book.asks else None
        down_bid = down_book.bids[0].price if down_book.bids else None
        down_ask = down_book.asks[0].price if down_book.asks else None
        pair_bid_sum = None if up_bid is None or down_bid is None else round(up_bid + down_bid, 4)
        pair_ask_sum = None if up_ask is None or down_ask is None else round(up_ask + down_ask, 4)
        up_before = state.up_inventory
        down_before = state.down_inventory

        if up_bid is None or down_bid is None:
            return {
                "slug": market.slug,
                "symbol": market.symbol,
                "timeframe_minutes": market.timeframe_minutes,
                "up_bid": up_bid,
                "up_ask": up_ask,
                "down_bid": down_bid,
                "down_ask": down_ask,
                "pair_bid_sum": pair_bid_sum,
                "pair_ask_sum": pair_ask_sum,
                "up_inventory_before": up_before,
                "down_inventory_before": down_before,
                "up_inventory_after": state.up_inventory,
                "down_inventory_after": state.down_inventory,
                "inventory_skew_before": round(up_before - down_before, 4),
                "inventory_skew_after": round(state.up_inventory - state.down_inventory, 4),
                "completed_pairs": state.completed_pairs,
                "realized_pnl": state.realized_pnl,
                "reward_pnl": state.reward_pnl,
                "net_pnl": round(state.realized_pnl + state.reward_pnl, 4),
                "status": "skipped",
            }

        size = 1.0
        up_skew = state.up_inventory - state.down_inventory
        down_skew = state.down_inventory - state.up_inventory
        up_quote = round(min(0.99, up_bid + self.config.quote_edge - max(0.0, up_skew) * self.config.skew_step), 2)
        down_quote = round(min(0.99, down_bid + self.config.quote_edge - max(0.0, down_skew) * self.config.skew_step), 2)
        up_quote = max(up_quote, up_bid)
        down_quote = max(down_quote, down_bid)

        paired = min(state.up_inventory, state.down_inventory)
        if paired >= 1.0 and pair_bid_sum is not None and pair_bid_sum >= 1.0 + self.config.quote_edge:
            state.up_inventory = round(state.up_inventory - 1.0, 4)
            state.down_inventory = round(state.down_inventory - 1.0, 4)
            state.completed_pairs = round(state.completed_pairs + 1.0, 4)
            state.realized_pnl = round(state.realized_pnl + (pair_bid_sum - 1.0), 4)
            return {
                "slug": market.slug,
                "symbol": market.symbol,
                "timeframe_minutes": market.timeframe_minutes,
                "up_bid": up_bid,
                "up_ask": up_ask,
                "down_bid": down_bid,
                "down_ask": down_ask,
                "up_quote": up_quote,
                "down_quote": down_quote,
                "sold_up": False,
                "sold_down": False,
                "pair_bid_sum": pair_bid_sum,
                "pair_ask_sum": pair_ask_sum,
                "up_inventory_before": up_before,
                "down_inventory_before": down_before,
                "up_inventory_after": state.up_inventory,
                "down_inventory_after": state.down_inventory,
                "inventory_skew_before": round(up_before - down_before, 4),
                "inventory_skew_after": round(state.up_inventory - state.down_inventory, 4),
                "completed_pairs": state.completed_pairs,
                "realized_pnl": state.realized_pnl,
                "reward_pnl": state.reward_pnl,
                "net_pnl": round(state.realized_pnl + state.reward_pnl, 4),
                "status": "pair_completed",
            }

        sold_up = up_ask is not None and up_quote <= up_ask and up_skew < self.config.max_skew
        sold_down = down_ask is not None and down_quote <= down_ask and down_skew < self.config.max_skew

        if sold_up and state.up_inventory > 0:
            state.up_inventory = round(state.up_inventory - size, 4)
            state.realized_pnl = round(state.realized_pnl + up_quote, 4)
            state.reward_pnl = round(state.reward_pnl + self.config.reward_per_trade_usd, 4)
        if sold_down and state.down_inventory > 0:
            state.down_inventory = round(state.down_inventory - size, 4)
            state.realized_pnl = round(state.realized_pnl + down_quote, 4)
            state.reward_pnl = round(state.reward_pnl + self.config.reward_per_trade_usd, 4)

        while state.up_inventory + 1.0 <= self.config.target_pairs and state.down_inventory + 1.0 <= self.config.target_pairs:
            state.up_inventory = round(state.up_inventory + 1.0, 4)
            state.down_inventory = round(state.down_inventory + 1.0, 4)
            if state.up_inventory >= self.config.target_pairs or state.down_inventory >= self.config.target_pairs:
                break

        return {
            "slug": market.slug,
            "symbol": market.symbol,
            "timeframe_minutes": market.timeframe_minutes,
            "up_bid": up_bid,
            "up_ask": up_ask,
            "down_bid": down_bid,
            "down_ask": down_ask,
            "up_quote": up_quote,
            "down_quote": down_quote,
            "sold_up": sold_up,
            "sold_down": sold_down,
            "pair_bid_sum": pair_bid_sum,
            "pair_ask_sum": pair_ask_sum,
            "up_inventory_before": up_before,
            "down_inventory_before": down_before,
            "up_inventory_after": state.up_inventory,
            "down_inventory_after": state.down_inventory,
            "inventory_skew_before": round(up_before - down_before, 4),
            "inventory_skew_after": round(state.up_inventory - state.down_inventory, 4),
            "completed_pairs": state.completed_pairs,
            "realized_pnl": state.realized_pnl,
            "reward_pnl": state.reward_pnl,
            "net_pnl": round(state.realized_pnl + state.reward_pnl, 4),
            "status": "quoted_pair_mm",
        }
