from __future__ import annotations

from src.clients.base import Market
from src.markets.market_parser import ParsedCryptoMarket, parse_crypto_market


def filter_supported_markets(markets: list[Market], symbols: set[str]) -> list[ParsedCryptoMarket]:
    out: list[ParsedCryptoMarket] = []
    for market in markets:
        parsed = parse_crypto_market(market)
        if parsed is None:
            continue
        if is_supported_market(parsed, symbols):
            out.append(parsed)
    return out


def is_supported_market(parsed: ParsedCryptoMarket, symbols: set[str]) -> bool:
    return parsed.symbol in symbols and parsed.timeframe_minutes == 5

