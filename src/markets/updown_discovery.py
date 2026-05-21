from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Iterable

from src.clients.polymarket_client import PolymarketClient
from src.markets.updown_parser import UpDownMarket, parse_updown_event

logger = logging.getLogger(__name__)

UPDOWN_PREFIXES = {
    "BTC": ("btc-updown-5m", "btc-updown-15m"),
    "ETH": ("eth-updown-5m", "eth-updown-15m"),
    "SOL": ("sol-updown-5m", "sol-updown-15m"),
    "XRP": ("xrp-updown-5m", "xrp-updown-15m"),
    "DOGE": ("doge-updown-5m", "doge-updown-15m"),
    "BNB": ("bnb-updown-5m", "bnb-updown-15m"),
    "HYPE": ("hype-updown-5m", "hype-updown-15m"),
}


async def discover_updown_markets(client: PolymarketClient, symbols: Iterable[str]) -> list[UpDownMarket]:
    normalized = [symbol.upper() for symbol in symbols]
    candidate_slugs = _build_candidate_slugs(normalized)
    events = await asyncio.gather(*(client.get_event_by_slug(slug) for slug in candidate_slugs))

    out: list[UpDownMarket] = []
    seen_slugs: set[str] = set()
    found_slugs: list[str] = []
    for event in events:
        if event is None:
            continue
        slug = str(event.get("slug") or "")
        found_slugs.append(slug)
        parsed = parse_updown_event(event)
        if parsed is None:
            continue
        if parsed.symbol not in normalized or parsed.slug in seen_slugs:
            continue
        out.append(parsed)
        seen_slugs.add(parsed.slug)

    logger.info(
        "updown discovery summary",
        extra={
            "symbols": normalized,
            "candidate_count": len(candidate_slugs),
            "found_count": len(found_slugs),
            "found_slugs": found_slugs[:10],
            "discovered_slugs": [market.slug for market in out[:10]],
        },
    )
    return out


def _build_candidate_slugs(symbols: Iterable[str], now: datetime | None = None) -> list[str]:
    current = now or datetime.now(UTC)
    current_ts = int(current.timestamp())
    candidates: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        prefixes = UPDOWN_PREFIXES.get(symbol.upper())
        if prefixes is None:
            continue
        for timeframe, prefix in ((5, prefixes[0]), (15, prefixes[1])):
            for expiry_ts in _candidate_expiry_timestamps(current_ts, timeframe):
                slug = f"{prefix}-{expiry_ts}"
                if slug in seen:
                    continue
                seen.add(slug)
                candidates.append(slug)
    return candidates


def _candidate_expiry_timestamps(current_ts: int, timeframe_minutes: int) -> list[int]:
    step = timeframe_minutes * 60
    anchor = (current_ts // step) * step
    return [anchor + (offset * step) for offset in range(-2, 5)]
