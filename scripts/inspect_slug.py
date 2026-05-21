from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.clients.polymarket_client import PolymarketClient
from src.config.settings import get_settings
from src.utils.logger import setup_logging


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


def print_event(raw: dict[str, Any]) -> None:
    print(f"title: {raw.get('title')}")
    print(f"slug: {raw.get('slug')}")
    print(f"id: {raw.get('id')}")
    print(f"category: {raw.get('category')}")
    print(f"active: {raw.get('active')}")
    print(f"closed: {raw.get('closed')}")
    print(f"startDate: {raw.get('startDate')}")
    print(f"endDate: {raw.get('endDate')}")
    markets = raw.get("markets") if isinstance(raw.get("markets"), list) else []
    print(f"markets_count: {len(markets)}")
    for index, market in enumerate(markets, start=1):
        print("-" * 80)
        print(f"[{index}] question: {market.get('question') or market.get('title')}")
        print(f"    conditionId: {market.get('conditionId')}")
        print(f"    slug: {market.get('slug')}")
        print(f"    endDate: {market.get('endDate')}")
        print(f"    active: {market.get('active')}")
        print(f"    closed: {market.get('closed')}")
        print(f"    outcomes: {market.get('outcomes')}")
        print(f"    clobTokenIds: {market.get('clobTokenIds')}")
        print(f"    bestAsk: {market.get('bestAsk')}")
        print(f"    lastTradePrice: {market.get('lastTradePrice')}")


async def main_async(slug: str, dump_json: str | None) -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    client = build_client()
    try:
        event = await client.get_event_by_slug(slug)
        if event is None:
            print(f"Event not found for slug: {slug}")
            return
        if dump_json:
            path = Path(dump_json)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(event, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            print(f"Saved JSON dump: {path}")
            print()
        print_event(event)
    finally:
        await client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect a Polymarket event by exact slug.")
    parser.add_argument("--slug", required=True, help="Event slug, e.g. btc-updown-5m-1779378600")
    parser.add_argument("--dump-json", type=str, default=None, help="Save raw event JSON to file")
    args = parser.parse_args()
    asyncio.run(main_async(slug=args.slug, dump_json=args.dump_json))


if __name__ == "__main__":
    main()

