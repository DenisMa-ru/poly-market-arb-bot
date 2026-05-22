from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from src.clients.base import Market, Outcome, Orderbook

REWARDS_BASE = "https://clob.polymarket.com"


@dataclass(frozen=True)
class RewardCandidate:
    market: Market
    condition_id: str
    question: str
    event_slug: str | None
    reward_rate_per_day: float | None
    rewards_max_spread: float | None
    rewards_min_size: float | None
    volume_24hr: float
    best_bid: float | None
    best_ask: float | None
    spread_bps: float | None
    priority_score: float


def _as_float(value: object) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _spread_bps(best_bid: float | None, best_ask: float | None) -> float | None:
    if best_bid is None or best_ask is None:
        return None
    mid = (best_bid + best_ask) / 2.0
    if mid <= 0:
        return None
    return round(((best_ask - best_bid) / mid) * 10000.0, 2)


def _priority_score(*, reward_rate_per_day: float | None, volume_24hr: float, spread_bps: float | None, rewards_max_spread: float | None) -> float:
    reward_component = reward_rate_per_day or 0.0
    volume_component = volume_24hr / 100000.0
    spread_component = 0.0 if spread_bps is None else min(spread_bps, 500.0) / 100.0
    eligibility_bonus = 2.0 if rewards_max_spread and rewards_max_spread > 0 else 0.0
    return round(reward_component + volume_component + spread_component + eligibility_bonus, 4)


async def fetch_reward_candidates(
    *,
    client,
    markets: list[Market],
    tag_slugs: list[str],
    limit: int,
    min_volume_24h: float = 0.0,
) -> list[RewardCandidate]:
    market_by_id = {market.market_id: market for market in markets if market.market_id}
    params: dict[str, Any] = {"limit": min(max(limit * 4, 100), 500), "sponsored": "true"}
    for tag in tag_slugs:
        params.setdefault("tag_slug", [])
        params["tag_slug"].append(tag)
    out: list[RewardCandidate] = []
    cursor: str | None = None
    async with httpx.AsyncClient(base_url=REWARDS_BASE, timeout=20.0) as rewards_client:
        while len(out) < limit:
            request_params = dict(params)
            if cursor:
                request_params["next_cursor"] = cursor
            response = await rewards_client.get("/rewards/markets/multi", params=request_params)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                break
            items = payload.get("data") or payload.get("markets") or payload.get("results") or []
            if not isinstance(items, list) or not items:
                break
            for item in items:
                if not isinstance(item, dict):
                    continue
                condition_id = str(item.get("condition_id") or item.get("conditionId") or "")
                market = market_by_id.get(condition_id)
                if market is None or not market.yes_token_id or not market.no_token_id:
                    continue
                volume_24hr = _as_float(item.get("volume_24hr")) or _as_float(item.get("volume24hr")) or _as_float(item.get("volume")) or 0.0
                if volume_24hr < min_volume_24h:
                    continue
                yes_book, no_book = await client.get_orderbook(market.yes_token_id, Outcome.YES), await client.get_orderbook(market.no_token_id, Outcome.NO)
                best_bid = yes_book.bids[0].price if yes_book.bids else None
                best_ask = yes_book.asks[0].price if yes_book.asks else None
                spread_bps = _spread_bps(best_bid, best_ask)
                reward_rate_per_day = _as_float(item.get("rate_per_day"))
                rewards_max_spread = _as_float(item.get("rewards_max_spread"))
                rewards_min_size = _as_float(item.get("rewards_min_size"))
                out.append(
                    RewardCandidate(
                        market=market,
                        condition_id=condition_id,
                        question=str(item.get("question") or market.question),
                        event_slug=str(item.get("event_slug")) if item.get("event_slug") is not None else None,
                        reward_rate_per_day=reward_rate_per_day,
                        rewards_max_spread=rewards_max_spread,
                        rewards_min_size=rewards_min_size,
                        volume_24hr=volume_24hr,
                        best_bid=best_bid,
                        best_ask=best_ask,
                        spread_bps=spread_bps,
                        priority_score=_priority_score(
                            reward_rate_per_day=reward_rate_per_day,
                            volume_24hr=volume_24hr,
                            spread_bps=spread_bps,
                            rewards_max_spread=rewards_max_spread,
                        ),
                    )
                )
            cursor_raw = payload.get("next_cursor")
            cursor = str(cursor_raw) if cursor_raw else None
            if not cursor or cursor == "LTE=" or len(items) < request_params["limit"]:
                break
    out.sort(key=lambda row: row.priority_score, reverse=True)
    return out[:limit]
