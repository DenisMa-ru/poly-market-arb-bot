from __future__ import annotations

import re
from dataclasses import dataclass

from src.clients.base import Market


@dataclass(frozen=True)
class ParsedCryptoMarket:
    market_id: str
    question: str
    symbol: str
    timeframe_minutes: int
    strike: float | None
    expiry_at: str | None
    yes_token_id: str
    no_token_id: str
    raw_market: Market


def parse_crypto_market(market: Market) -> ParsedCryptoMarket | None:
    if market.yes_token_id is None or market.no_token_id is None:
        return None
    symbol = _extract_symbol(market.question)
    timeframe = _extract_timeframe_minutes(market.question)
    if symbol is None or timeframe is None:
        return None
    return ParsedCryptoMarket(
        market_id=market.market_id,
        question=market.question,
        symbol=symbol,
        timeframe_minutes=timeframe,
        strike=_extract_strike(market.question),
        expiry_at=market.closes_at_iso,
        yes_token_id=market.yes_token_id,
        no_token_id=market.no_token_id,
        raw_market=market,
    )


def _extract_symbol(question: str) -> str | None:
    upper = question.upper()
    for symbol in ("BTC", "BITCOIN", "ETH", "ETHEREUM"):
        if symbol in upper:
            return "BTC" if symbol in ("BTC", "BITCOIN") else "ETH"
    return None


def _extract_timeframe_minutes(question: str) -> int | None:
    match = re.search(r"(\d+)\s*-?\s*MIN", question.upper())
    if match:
        return int(match.group(1))
    return None


def _extract_strike(question: str) -> float | None:
    match = re.search(r"(?:ABOVE|OVER|HIGHER THAN)\s+\$?([0-9][0-9,]*(?:\.[0-9]+)?)", question.upper())
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None

