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
    paired_inventory: float = 0.0
    free_up: float = 0.0
    free_down: float = 0.0
    realized_pnl: float = 0.0
    reward_pnl: float = 0.0
    completed_pairs: float = 0.0
    split_notional: float = 0.0


class PairMarketMaker:
    def __init__(self, config: PairMarketMakerConfig) -> None:
        self.config = config

    @staticmethod
    def _mark_value(*, paired_inventory: float, free_up: float, free_down: float, up_bid: float | None, down_bid: float | None) -> float:
        if up_bid is None or down_bid is None:
            return 0.0
        return round((paired_inventory * (up_bid + down_bid)) + (free_up * up_bid) + (free_down * down_bid), 4)

    def evaluate(self, market: UpDownMarket, up_book: Orderbook, down_book: Orderbook, state: PairMarketMakerState) -> dict[str, object]:
        up_bid = up_book.bids[0].price if up_book.bids else None
        up_ask = up_book.asks[0].price if up_book.asks else None
        down_bid = down_book.bids[0].price if down_book.bids else None
        down_ask = down_book.asks[0].price if down_book.asks else None
        pair_bid_sum = None if up_bid is None or down_bid is None else round(up_bid + down_bid, 4)
        pair_ask_sum = None if up_ask is None or down_ask is None else round(up_ask + down_ask, 4)
        paired_before = state.paired_inventory
        free_up_before = state.free_up
        free_down_before = state.free_down
        total_up_before = paired_before + free_up_before
        total_down_before = paired_before + free_down_before
        skew_before = round(total_up_before - total_down_before, 4)
        mark_before = self._mark_value(
            paired_inventory=paired_before,
            free_up=free_up_before,
            free_down=free_down_before,
            up_bid=up_bid,
            down_bid=down_bid,
        )

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
                "paired_inventory_before": paired_before,
                "paired_inventory_after": state.paired_inventory,
                "free_up_before": free_up_before,
                "free_down_before": free_down_before,
                "free_up_after": state.free_up,
                "free_down_after": state.free_down,
                "up_inventory_before": total_up_before,
                "down_inventory_before": total_down_before,
                "up_inventory_after": state.paired_inventory + state.free_up,
                "down_inventory_after": state.paired_inventory + state.free_down,
                "inventory_skew_before": skew_before,
                "inventory_skew_after": round((state.paired_inventory + state.free_up) - (state.paired_inventory + state.free_down), 4),
                "mark_value_before": mark_before,
                "mark_value_after": mark_before,
                "completed_pairs": state.completed_pairs,
                "split_notional": state.split_notional,
                "split_pairs": 0.0,
                "realized_pnl": state.realized_pnl,
                "reward_pnl": state.reward_pnl,
                "skew_mark_pnl": 0.0,
                "net_pnl": round(state.realized_pnl + state.reward_pnl, 4),
                "status": "skipped",
            }

        size = 1.0
        total_up = state.paired_inventory + state.free_up
        total_down = state.paired_inventory + state.free_down
        up_skew = total_up - total_down
        down_skew = total_down - total_up
        up_quote = round(min(0.99, up_bid + self.config.quote_edge - max(0.0, up_skew) * self.config.skew_step), 2)
        down_quote = round(min(0.99, down_bid + self.config.quote_edge - max(0.0, down_skew) * self.config.skew_step), 2)
        up_quote = max(up_quote, up_bid)
        down_quote = max(down_quote, down_bid)

        paired = state.paired_inventory
        if paired >= 1.0 and pair_bid_sum is not None and pair_bid_sum >= 1.0 + self.config.quote_edge:
            state.paired_inventory = round(state.paired_inventory - 1.0, 4)
            state.completed_pairs = round(state.completed_pairs + 1.0, 4)
            state.realized_pnl = round(state.realized_pnl + (pair_bid_sum - 1.0), 4)
            mark_after = self._mark_value(
                paired_inventory=state.paired_inventory,
                free_up=state.free_up,
                free_down=state.free_down,
                up_bid=up_bid,
                down_bid=down_bid,
            )
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
                "paired_inventory_before": paired_before,
                "paired_inventory_after": state.paired_inventory,
                "free_up_before": free_up_before,
                "free_down_before": free_down_before,
                "free_up_after": state.free_up,
                "free_down_after": state.free_down,
                "up_inventory_before": total_up_before,
                "down_inventory_before": total_down_before,
                "up_inventory_after": state.paired_inventory + state.free_up,
                "down_inventory_after": state.paired_inventory + state.free_down,
                "inventory_skew_before": skew_before,
                "inventory_skew_after": round((state.paired_inventory + state.free_up) - (state.paired_inventory + state.free_down), 4),
                "mark_value_before": mark_before,
                "mark_value_after": mark_after,
                "completed_pairs": state.completed_pairs,
                "split_notional": state.split_notional,
                "split_pairs": 0.0,
                "realized_pnl": state.realized_pnl,
                "reward_pnl": state.reward_pnl,
                "skew_mark_pnl": round(mark_after - mark_before, 4),
                "net_pnl": round(state.realized_pnl + state.reward_pnl + (mark_after - mark_before), 4),
                "status": "pair_completed",
            }

        sold_up = up_ask is not None and up_quote <= up_ask and up_skew < self.config.max_skew
        sold_down = down_ask is not None and down_quote <= down_ask and down_skew < self.config.max_skew

        if sold_up and state.paired_inventory > 0:
            state.paired_inventory = round(state.paired_inventory - size, 4)
            state.free_down = round(state.free_down + size, 4)
            state.realized_pnl = round(state.realized_pnl + (up_quote - 0.5), 4)
            state.reward_pnl = round(state.reward_pnl + self.config.reward_per_trade_usd, 4)
        if sold_down and state.paired_inventory > 0:
            state.paired_inventory = round(state.paired_inventory - size, 4)
            state.free_up = round(state.free_up + size, 4)
            state.realized_pnl = round(state.realized_pnl + (down_quote - 0.5), 4)
            state.reward_pnl = round(state.reward_pnl + self.config.reward_per_trade_usd, 4)

        repair_size = min(state.free_up, state.free_down)
        if repair_size > 0:
            state.free_up = round(state.free_up - repair_size, 4)
            state.free_down = round(state.free_down - repair_size, 4)
            state.paired_inventory = round(state.paired_inventory + repair_size, 4)

        split_pairs = 0.0
        if state.paired_inventory < self.config.target_pairs:
            split_pairs = round(self.config.target_pairs - state.paired_inventory, 4)
            state.paired_inventory = round(state.paired_inventory + split_pairs, 4)
            state.split_notional = round(state.split_notional + split_pairs, 4)
            state.realized_pnl = round(state.realized_pnl - split_pairs, 4)

        mark_after = self._mark_value(
            paired_inventory=state.paired_inventory,
            free_up=state.free_up,
            free_down=state.free_down,
            up_bid=up_bid,
            down_bid=down_bid,
        )
        total_up_after = state.paired_inventory + state.free_up
        total_down_after = state.paired_inventory + state.free_down
        skew_mark_pnl = round(mark_after - mark_before, 4)

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
            "paired_inventory_before": paired_before,
            "paired_inventory_after": state.paired_inventory,
            "free_up_before": free_up_before,
            "free_down_before": free_down_before,
            "free_up_after": state.free_up,
            "free_down_after": state.free_down,
            "up_inventory_before": total_up_before,
            "down_inventory_before": total_down_before,
            "up_inventory_after": total_up_after,
            "down_inventory_after": total_down_after,
            "inventory_skew_before": skew_before,
            "inventory_skew_after": round(total_up_after - total_down_after, 4),
            "mark_value_before": mark_before,
            "mark_value_after": mark_after,
            "completed_pairs": state.completed_pairs,
            "split_notional": state.split_notional,
            "split_pairs": split_pairs,
            "realized_pnl": state.realized_pnl,
            "reward_pnl": state.reward_pnl,
            "skew_mark_pnl": skew_mark_pnl,
            "net_pnl": round(state.realized_pnl + state.reward_pnl + skew_mark_pnl, 4),
            "status": "quoted_pair_mm",
        }
