from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.clients.polymarket_client import PolymarketClient
from src.config.settings import get_settings
from src.markets.market_parser import explain_rejection, parse_crypto_market
from src.utils.logger import setup_logging


def _looks_crypto_related(question: str) -> bool:
    upper = question.upper()
    return any(token in upper for token in ("BTC", "BITCOIN", "ETH", "ETHEREUM", "5 MIN", "5M", "15 MIN", "15M"))


def _matches_search(question: str, search: str | None) -> bool:
    if not search:
        return True
    return search.upper() in question.upper()


def _print_summary(markets: list) -> None:
    counts = {
        "btc": 0,
        "eth": 0,
        "5m": 0,
        "15m": 0,
        "recognized": 0,
    }
    for market in markets:
        upper = market.question.upper()
        if "BTC" in upper or "BITCOIN" in upper:
            counts["btc"] += 1
        if "ETH" in upper or "ETHEREUM" in upper:
            counts["eth"] += 1
        if any(token in upper for token in ("5 MIN", "5M", "5 MINUTE", "5 MINUTES")):
            counts["5m"] += 1
        if any(token in upper for token in ("15 MIN", "15M", "15 MINUTE", "15 MINUTES")):
            counts["15m"] += 1
        if parse_crypto_market(market) is not None:
            counts["recognized"] += 1
    print("Summary:")
    for key, value in counts.items():
        print(f"  {key}: {value}")
    print()


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


async def main_async(limit: int, only_recognized: bool, search: str | None, dump_json: str | None) -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    client = build_client()
    try:
        markets = await client.list_markets(active_only=True)
        crypto_like = [market for market in markets if _looks_crypto_related(market.question) and _matches_search(market.question, search)]
        print(f"Active markets fetched: {len(markets)}")
        print(f"Crypto-like questions: {len(crypto_like)}")
        print()
        _print_summary(crypto_like)

        if dump_json:
            dump_path = Path(dump_json)
            dump_path.parent.mkdir(parents=True, exist_ok=True)
            payload = [
                {
                    "market_id": market.market_id,
                    "question": market.question,
                    "category": market.category,
                    "outcomes": market.outcomes,
                    "yes_token_id": market.yes_token_id,
                    "no_token_id": market.no_token_id,
                    "expiry": market.closes_at_iso,
                    "raw": market.raw,
                }
                for market in crypto_like
            ]
            dump_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            print(f"Saved JSON dump: {dump_path}")
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
                print(f"reason: {explain_rejection(market)}")
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
    parser.add_argument("--search", type=str, default=None, help="Filter by substring in question")
    parser.add_argument("--dump-json", type=str, default=None, help="Save matching markets to JSON file")
    args = parser.parse_args()
    asyncio.run(
        main_async(
            limit=args.limit,
            only_recognized=args.recognized_only,
            search=args.search,
            dump_json=args.dump_json,
        )
    )


if __name__ == "__main__":
    main()
