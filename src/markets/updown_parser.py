from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class UpDownMarket:
    event_id: str
    market_id: str
    slug: str
    question: str
    symbol: str
    timeframe_minutes: int
    expiry_at: str | None
    up_token_id: str
    down_token_id: str
    raw_event: dict[str, Any]
    raw_market: dict[str, Any]


def parse_updown_event(event: dict[str, Any]) -> UpDownMarket | None:
    slug = str(event.get("slug") or "")
    slug_match = re.match(r"^(btc|eth|sol|xrp|doge|bnb|hype)-updown-(5m|15m)-", slug)
    if not slug_match:
        return None
    symbol = slug_match.group(1).upper()
    timeframe_minutes = 5 if slug_match.group(2) == "5m" else 15
    markets = event.get("markets") if isinstance(event.get("markets"), list) else []
    if len(markets) != 1:
        return None
    market = markets[0]
    outcomes_raw = market.get("outcomes") or '["Up", "Down"]'
    outcomes = _parse_string_list(outcomes_raw)
    if len(outcomes) != 2 or outcomes[0].upper() != "UP" or outcomes[1].upper() != "DOWN":
        return None
    token_ids = _parse_string_list(market.get("clobTokenIds") or "[]")
    if len(token_ids) < 2:
        return None
    return UpDownMarket(
        event_id=str(event.get("id") or ""),
        market_id=str(market.get("conditionId") or market.get("id") or slug),
        slug=slug,
        question=str(market.get("question") or market.get("title") or event.get("title") or slug),
        symbol=symbol,
        timeframe_minutes=timeframe_minutes,
        expiry_at=market.get("endDate") or event.get("endDate"),
        up_token_id=str(token_ids[0]),
        down_token_id=str(token_ids[1]),
        raw_event=event,
        raw_market=market,
    )


def _parse_string_list(value: object) -> list[str]:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return [str(item) for item in parsed] if isinstance(parsed, list) else []
    if isinstance(value, list):
        return [str(item) for item in value]
    return []

