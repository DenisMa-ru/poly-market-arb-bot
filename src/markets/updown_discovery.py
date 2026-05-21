from __future__ import annotations

import logging
from typing import Iterable

from src.clients.polymarket_client import PolymarketClient
from src.markets.updown_parser import UpDownMarket, parse_updown_event

logger = logging.getLogger(__name__)

UPDOWN_PREFIXES = {
    "BTC": ("btc-updown-5m", "btc-updown-15m"),
    "ETH": ("eth-updown-5m", "eth-updown-15m"),
    "SOL": ("sol-updown-5m", "sol-updown-15m"),
}


async def discover_updown_markets(client: PolymarketClient, symbols: Iterable[str]) -> list[UpDownMarket]:
    normalized = [symbol.upper() for symbol in symbols]
    events = await client.list_events(active_only=True, limit=500)
    matching_slug_count = 0
    out: list[UpDownMarket] = []
    for event in events:
        slug = str(event.get("slug") or "")
        if "-updown-" in slug:
            matching_slug_count += 1
        parsed = parse_updown_event(event)
        if parsed is None:
            continue
        if parsed.symbol not in normalized:
            continue
        out.append(parsed)
    logger.info(
        "updown discovery summary",
        extra={
            "events_fetched": len(events),
            "matching_slug_count": matching_slug_count,
            "symbols": normalized,
            "sample_slugs": [str(event.get("slug") or "") for event in events[:10]],
            "discovered_slugs": [market.slug for market in out[:10]],
        },
    )
    return out
