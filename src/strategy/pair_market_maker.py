from __future__ import annotations

from dataclasses import dataclass

from src.clients.base import Orderbook
from src.markets.updown_parser import UpDownMarket


@dataclass(frozen=True)
class PairMarketMakerConfig:
    enabled: bool
    markets_limit: int
    target_pairs: float
    min_paired_inventory: float
    replenish_batch_size: float
    max_free_inventory_per_side: float
    quote_edge: float
    skew_step: float
    max_skew: float
    min_new_skew_edge: float
    reward_per_trade_usd: float
    reward_bps_per_trade: float = 0.0


FILL_BUFFER = 0.02


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

    def _reward_for_trade(self, *, quote: float, size: float) -> float:
        reward = self.config.reward_per_trade_usd
        if self.config.reward_bps_per_trade > 0:
            reward += quote * size * (self.config.reward_bps_per_trade / 10000.0)
        return round(reward, 4)

    def evaluate(
        self,
        market: UpDownMarket,
        up_book: Orderbook,
        down_book: Orderbook,
        state: PairMarketMakerState,
        *,
        remaining_fill_budget: int | None = None,
    ) -> dict[str, object]:
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
        realized_before = state.realized_pnl
        reward_before = state.reward_pnl
        completed_pairs_before = state.completed_pairs
        split_notional_before = state.split_notional
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
                "completed_pairs_delta": 0.0,
                "split_notional": state.split_notional,
                "split_notional_delta": 0.0,
                "split_pairs": 0.0,
                "realized_pnl": state.realized_pnl,
                "realized_pnl_delta": 0.0,
                "reward_pnl": state.reward_pnl,
                "reward_pnl_delta": 0.0,
                "skew_mark_pnl": 0.0,
                "net_pnl": round(state.realized_pnl + state.reward_pnl, 4),
                "net_pnl_delta": 0.0,
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
        if state.free_up > 0 and up_ask is not None and state.free_down <= 0:
            up_quote = up_ask
        if state.free_down > 0 and down_ask is not None and state.free_up <= 0:
            down_quote = down_ask

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
                "completed_pairs_delta": round(state.completed_pairs - completed_pairs_before, 4),
                "split_notional": state.split_notional,
                "split_notional_delta": round(state.split_notional - split_notional_before, 4),
                "split_pairs": 0.0,
                "realized_pnl": state.realized_pnl,
                "realized_pnl_delta": round(state.realized_pnl - realized_before, 4),
                "reward_pnl": state.reward_pnl,
                "reward_pnl_delta": round(state.reward_pnl - reward_before, 4),
                "skew_mark_pnl": round(mark_after - mark_before, 4),
                "net_pnl": round(state.realized_pnl + state.reward_pnl + (mark_after - mark_before), 4),
                "net_pnl_delta": round((state.realized_pnl - realized_before) + (state.reward_pnl - reward_before) + (mark_after - mark_before), 4),
                "status": "pair_completed",
            }

        up_fill_edge = None if up_ask is None else round(up_ask - up_quote, 4)
        down_fill_edge = None if down_ask is None else round(down_ask - down_quote, 4)

        sold_up_candidate = (
            up_ask is not None
            and up_quote <= up_ask
            and up_fill_edge is not None
            and up_fill_edge <= FILL_BUFFER
            and up_skew < self.config.max_skew
            and (state.paired_inventory > 0 or state.free_up > 0)
            and state.free_down <= 0
        )
        sold_down_candidate = (
            down_ask is not None
            and down_quote <= down_ask
            and down_fill_edge is not None
            and down_fill_edge <= FILL_BUFFER
            and down_skew < self.config.max_skew
            and (state.paired_inventory > 0 or state.free_down > 0)
            and state.free_up <= 0
        )

        sold_up = False
        sold_down = False
        if sold_up_candidate and sold_down_candidate:
            up_edge = up_fill_edge if up_fill_edge is not None else -1.0
            down_edge = down_fill_edge if down_fill_edge is not None else -1.0
            if up_edge > down_edge:
                sold_up = True
            elif down_edge > up_edge:
                sold_down = True
            elif up_skew < down_skew:
                sold_up = True
            elif down_skew < up_skew:
                sold_down = True
            else:
                sold_up = up_quote >= down_quote
                sold_down = not sold_up
        else:
            sold_up = sold_up_candidate
            sold_down = sold_down_candidate

        fills_allowed = remaining_fill_budget is None or remaining_fill_budget > 0
        if not fills_allowed:
            sold_up = False
            sold_down = False

        if sold_up and state.free_up <= 0 and up_quote - 0.5 < self.config.min_new_skew_edge:
            sold_up = False
        if sold_down and state.free_down <= 0 and down_quote - 0.5 < self.config.min_new_skew_edge:
            sold_down = False

        if sold_up:
            unwind_size = min(size, state.free_up)
            if unwind_size > 0:
                state.free_up = round(state.free_up - unwind_size, 4)
                state.realized_pnl = round(state.realized_pnl + up_quote * unwind_size, 4)
            else:
                state.paired_inventory = round(state.paired_inventory - size, 4)
                state.free_down = round(state.free_down + size, 4)
                state.realized_pnl = round(state.realized_pnl + (up_quote - 0.5), 4)
            state.reward_pnl = round(state.reward_pnl + self._reward_for_trade(quote=up_quote, size=size), 4)
        if sold_down:
            unwind_size = min(size, state.free_down)
            if unwind_size > 0:
                state.free_down = round(state.free_down - unwind_size, 4)
                state.realized_pnl = round(state.realized_pnl + down_quote * unwind_size, 4)
            else:
                state.paired_inventory = round(state.paired_inventory - size, 4)
                state.free_up = round(state.free_up + size, 4)
                state.realized_pnl = round(state.realized_pnl + (down_quote - 0.5), 4)
            state.reward_pnl = round(state.reward_pnl + self._reward_for_trade(quote=down_quote, size=size), 4)

        repair_size = min(state.free_up, state.free_down)
        if repair_size > 0:
            state.free_up = round(state.free_up - repair_size, 4)
            state.free_down = round(state.free_down - repair_size, 4)
            state.paired_inventory = round(state.paired_inventory + repair_size, 4)
            state.completed_pairs = round(state.completed_pairs + repair_size, 4)

        split_pairs = 0.0
        free_inventory_total = round(state.free_up + state.free_down, 4)
        has_fresh_one_sided_fill = sold_up or sold_down
        has_open_free_inventory = state.free_up > 0 or state.free_down > 0
        can_replenish = True
        if self.config.max_free_inventory_per_side > 0:
            can_replenish = (
                max(state.free_up, state.free_down) < self.config.max_free_inventory_per_side
                and free_inventory_total < self.config.max_free_inventory_per_side
            )
        replenish_ceiling = min(self.config.target_pairs, self.config.min_paired_inventory)
        needs_replenish = state.paired_inventory < replenish_ceiling
        if can_replenish and needs_replenish and not has_fresh_one_sided_fill and not has_open_free_inventory:
            replenish_target = min(self.config.target_pairs, state.paired_inventory + self.config.replenish_batch_size)
            split_pairs = round(replenish_target - state.paired_inventory, 4)
        if split_pairs > 0:
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
        realized_delta = round(state.realized_pnl - realized_before, 4)
        reward_delta = round(state.reward_pnl - reward_before, 4)
        completed_pairs_delta = round(state.completed_pairs - completed_pairs_before, 4)
        split_notional_delta = round(state.split_notional - split_notional_before, 4)
        net_pnl_delta = round(realized_delta + reward_delta + skew_mark_pnl, 4)

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
            "completed_pairs_delta": completed_pairs_delta,
            "split_notional": state.split_notional,
            "split_notional_delta": split_notional_delta,
            "split_pairs": split_pairs,
            "realized_pnl": state.realized_pnl,
            "realized_pnl_delta": realized_delta,
            "reward_pnl": state.reward_pnl,
            "reward_pnl_delta": reward_delta,
            "skew_mark_pnl": skew_mark_pnl,
            "net_pnl": round(state.realized_pnl + state.reward_pnl + skew_mark_pnl, 4),
            "net_pnl_delta": net_pnl_delta,
            "status": "quoted_pair_mm",
        }
