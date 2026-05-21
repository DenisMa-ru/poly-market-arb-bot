from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.clients.polymarket_client import PolymarketClient
from src.config.settings import get_settings
from src.markets.market_parser import parse_crypto_market
from src.utils.logger import setup_logging


def _looks_crypto_related(question: str) -> bool:
    upper = question.upper()
    return any(token in upper for token in ("BTC", "BITCOIN", "ETH", "ETHEREUM", "5 MIN", "5M", "15 MIN", "15M"))


def build_client() -> PolymarketClient:
    settings = get_settings()
    settings.assert_polymarket_ready()
    return PolymarketClient(
        private_key=settings.polymarket_pk,
        host=settings.polymarket_host,
        chain_id=settings.polymarket_chain_id,
        signature_type=settings.polymarket_signature_type,
        funder=settings.polymarket_funder or None,
    )


async def main_async(limit: int, only_recognized: bool) -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    client = build_client()
    try:
        markets = await client.list_markets(active_only=True)
        crypto_like = [market for market in markets if _looks_crypto_related(market.question)]
        print(f"Active markets fetched: {len(markets)}")
        print(f"Crypto-like questions: {len(crypto_like)}")
        print()

        shown = 0
        for market in crypto_like:
            parsed = parse_crypto_market(market)
            if only_recognized and parsed is None:
                continue
            print("-" * 80)
            print(f"question: {market.question}")
            print(f"market_id: {market.market_id}")
            print(f"category: {market.category}")
            print(f"outcomes: {market.outcomes}")
            print(f"yes_token_id: {market.yes_token_id}")
            print(f"no_token_id: {market.no_token_id}")
            print(f"expiry: {market.closes_at_iso}")
            if parsed is None:
                print("parser: NOT RECOGNIZED")
            else:
                print(
                    "parser:",
                    {
                        "symbol": parsed.symbol,
                        "timeframe_minutes": parsed.timeframe_minutes,
                        "strike": parsed.strike,
                    },
                )
            shown += 1
            if shown >= limit:
                break

        if shown == 0:
            print("No matching markets to show.")
    finally:
        await client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect active Polymarket markets and parser recognition.")
    parser.add_argument("--limit", type=int, default=50, help="Maximum number of markets to print")
    parser.add_argument("--recognized-only", action="store_true", help="Show only markets recognized by parser")
    args = parser.parse_args()
    asyncio.run(main_async(limit=args.limit, only_recognized=args.recognized_only))


if __name__ == "__main__":
    main()

