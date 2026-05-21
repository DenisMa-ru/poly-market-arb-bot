from __future__ import annotations

from typing import Iterable

from src.clients.polymarket_client import PolymarketClient
from src.markets.updown_parser import UpDownMarket, parse_updown_event

UPDOWN_PREFIXES = {
    "BTC": ("btc-updown-5m", "btc-updown-15m"),
    "ETH": ("eth-updown-5m", "eth-updown-15m"),
    "SOL": ("sol-updown-5m", "sol-updown-15m"),
}


async def discover_updown_markets(client: PolymarketClient, symbols: Iterable[str]) -> list[UpDownMarket]:
    normalized = [symbol.upper() for symbol in symbols]
    events = await client.list_events(active_only=True, limit=500)
    out: list[UpDownMarket] = []
    for event in events:
        parsed = parse_updown_event(event)
        if parsed is None:
            continue
        if parsed.symbol not in normalized:
            continue
        out.append(parsed)
    return out

