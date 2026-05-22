from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RewardMarketMakerConfig:
    enabled: bool
    target_spread_bps: float
    order_size: float
    max_inventory_per_market: float
    inventory_bias_bps: float
    daily_loss_limit_usd: float


@dataclass
class RewardMarketMakerState:
    inventory_yes: float = 0.0
    inventory_no: float = 0.0
    realized_pnl: float = 0.0
    reward_pnl: float = 0.0
    fills: int = 0
    quoted_cycles: int = 0


class RewardMarketMaker:
    def __init__(self, config: RewardMarketMakerConfig) -> None:
        self.config = config

    def evaluate(
        self,
        *,
        slug: str,
        question: str,
        best_bid: float | None,
        best_ask: float | None,
        reward_rate_per_day: float | None,
        rewards_max_spread: float | None,
        rewards_min_size: float | None,
        volume_24hr: float,
        state: RewardMarketMakerState,
    ) -> dict[str, object]:
        if best_bid is None or best_ask is None or best_bid > best_ask:
            return {
                "slug": slug,
                "question": question,
                "status": "skipped",
                "best_bid": best_bid,
                "best_ask": best_ask,
            }

        mid = round((best_bid + best_ask) / 2.0, 4)
        base_half_spread = max(mid * (self.config.target_spread_bps / 10000.0) / 2.0, 0.005)
        net_inventory = state.inventory_yes - state.inventory_no
        inventory_ratio = 0.0
        if self.config.max_inventory_per_market > 0:
            inventory_ratio = max(min(net_inventory / self.config.max_inventory_per_market, 1.0), -1.0)
        inventory_shift = mid * ((self.config.inventory_bias_bps / 10000.0) * inventory_ratio)

        bid_yes = round(max(0.01, mid - base_half_spread - max(0.0, inventory_shift)), 2)
        ask_yes = round(min(0.99, mid + base_half_spread - min(0.0, inventory_shift)), 2)
        bid_no = round(max(0.01, 1.0 - ask_yes), 2)
        ask_no = round(min(0.99, 1.0 - bid_yes), 2)
        quoted_spread_bps = round(((ask_yes - bid_yes) / mid) * 10000.0, 2) if mid > 0 else None

        state.quoted_cycles += 1
        eligible_spread = rewards_max_spread is None or rewards_max_spread <= 0 or (quoted_spread_bps is not None and quoted_spread_bps <= rewards_max_spread * 100)
        eligible_size = rewards_min_size is None or rewards_min_size <= 0 or self.config.order_size >= rewards_min_size
        reward_eligible = eligible_spread and eligible_size

        filled_bid = bid_yes >= best_ask
        filled_ask = ask_yes <= best_bid and state.inventory_yes > 0
        inventory_blocked = abs(net_inventory) >= self.config.max_inventory_per_market if self.config.max_inventory_per_market > 0 else False
        if inventory_blocked and net_inventory > 0:
            filled_bid = False
        if inventory_blocked and net_inventory < 0:
            filled_ask = False

        realized_delta = 0.0
        if filled_bid:
            state.inventory_yes = round(state.inventory_yes + self.config.order_size, 4)
            state.inventory_no = round(state.inventory_no - self.config.order_size, 4)
            state.fills += 1
        if filled_ask:
            sell_size = min(self.config.order_size, state.inventory_yes)
            state.inventory_yes = round(state.inventory_yes - sell_size, 4)
            state.inventory_no = round(state.inventory_no + sell_size, 4)
            realized_delta = round((ask_yes - mid) * sell_size, 4)
            state.realized_pnl = round(state.realized_pnl + realized_delta, 4)
            state.fills += 1

        reward_delta = 0.0
        if reward_eligible:
            reward_delta = round((reward_rate_per_day or 0.0) / 86400.0 * 2.0, 6)
            state.reward_pnl = round(state.reward_pnl + reward_delta, 6)

        net_inventory_after = round(state.inventory_yes - state.inventory_no, 4)
        mark_pnl = round(net_inventory_after * (best_bid - mid), 4)
        net_pnl = round(state.realized_pnl + state.reward_pnl + mark_pnl, 4)
        fill_rate = round(state.fills / state.quoted_cycles, 4) if state.quoted_cycles > 0 else 0.0
        status = "quoted_reward_mm"
        if inventory_blocked:
            status = "inventory_blocked"
        elif filled_bid and filled_ask:
            status = "two_sided_fill"
        elif filled_bid:
            status = "bid_fill"
        elif filled_ask:
            status = "ask_fill"

        return {
            "slug": slug,
            "question": question,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mid_price": mid,
            "bid_yes": bid_yes,
            "ask_yes": ask_yes,
            "bid_no": bid_no,
            "ask_no": ask_no,
            "quoted_spread_bps": quoted_spread_bps,
            "reward_rate_per_day": reward_rate_per_day,
            "rewards_max_spread": rewards_max_spread,
            "rewards_min_size": rewards_min_size,
            "reward_eligible": reward_eligible,
            "filled_bid": filled_bid,
            "filled_ask": filled_ask,
            "fill_rate": fill_rate,
            "inventory_yes": state.inventory_yes,
            "inventory_no": state.inventory_no,
            "net_inventory": net_inventory_after,
            "realized_pnl": state.realized_pnl,
            "realized_pnl_delta": realized_delta,
            "reward_pnl": state.reward_pnl,
            "reward_pnl_delta": reward_delta,
            "mark_pnl": mark_pnl,
            "net_pnl": net_pnl,
            "volume_24hr": volume_24hr,
            "status": status,
        }
