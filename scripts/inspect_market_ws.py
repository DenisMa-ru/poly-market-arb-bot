from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import websockets

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.config.settings import get_settings
from src.markets.updown_discovery import discover_updown_markets
from src.clients.polymarket_client import PolymarketClient
from src.utils.logger import setup_logging

WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"


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


async def _pick_token() -> tuple[str, str]:
    client = build_client()
    try:
        markets = await discover_updown_markets(client, get_settings().normalized_symbols())
        if not markets:
            raise RuntimeError("No up/down markets discovered")
        market = markets[0]
        return market.slug, market.up_token_id
    finally:
        await client.close()


async def main_async(token_id: str | None, attempts: int) -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    slug = "manual"
    if token_id is None:
        slug, token_id = await _pick_token()
    print(f"Using slug={slug} token_id={token_id}")

    payloads = [
        {"assets_ids": [token_id], "type": "market"},
        {"asset_ids": [token_id], "type": "market"},
        {"assets_ids": [token_id]},
        {"asset_ids": [token_id]},
    ]

    async with websockets.connect(WS_URL, ping_interval=20, ping_timeout=20) as ws:
        for index, payload in enumerate(payloads[:attempts], start=1):
            print(f"\n--- subscribe attempt {index} ---")
            print(json.dumps(payload, ensure_ascii=False))
            await ws.send(json.dumps(payload))
            for _ in range(3):
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=5)
                except TimeoutError:
                    print("timeout waiting for message")
                    break
                print(raw)


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose Polymarket market websocket subscription format.")
    parser.add_argument("--token-id", default=None, help="Optional token id to subscribe manually")
    parser.add_argument("--attempts", type=int, default=4, help="How many payload variants to try")
    args = parser.parse_args()
    asyncio.run(main_async(token_id=args.token_id, attempts=args.attempts))


if __name__ == "__main__":
    main()
