from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.clients.polymarket_client import GAMMA_BASE
from src.utils.logger import setup_logging


def _event_text(raw: dict[str, Any]) -> str:
    title = raw.get("title") or raw.get("question") or raw.get("slug") or ""
    return str(title)


def _looks_interesting(text: str) -> bool:
    upper = text.upper()
    return any(token in upper for token in ("BTC", "BITCOIN", "ETH", "ETHEREUM", "CRYPTO", "5 MIN", "5M", "15 MIN", "15M"))


def _matches_search(text: str, search: str | None) -> bool:
    if not search:
        return True
    return search.upper() in text.upper()


async def fetch_events(limit: int = 200, active_only: bool = True) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"limit": min(limit, 500), "offset": 0}
    if active_only:
        params["active"] = "true"
        params["closed"] = "false"
    out: list[dict[str, Any]] = []
    async with httpx.AsyncClient(base_url=GAMMA_BASE, timeout=20.0) as client:
        while len(out) < limit:
            response = await client.get("/events", params=params)
            response.raise_for_status()
            page = response.json()
            if not page:
                break
            if not isinstance(page, list):
                break
            out.extend(page)
            if len(page) < params["limit"]:
                break
            params["offset"] += params["limit"]
    return out[:limit]


def print_event(raw: dict[str, Any]) -> None:
    print("=" * 100)
    print(f"title: {_event_text(raw)}")
    print(f"slug: {raw.get('slug')}")
    print(f"id: {raw.get('id')}")
    print(f"category: {raw.get('category')}")
    print(f"active: {raw.get('active')}")
    print(f"closed: {raw.get('closed')}")
    print(f"startDate: {raw.get('startDate')}")
    print(f"endDate: {raw.get('endDate')}")
    markets = raw.get("markets") if isinstance(raw.get("markets"), list) else []
    print(f"markets_count: {len(markets)}")
    for index, market in enumerate(markets[:10], start=1):
        question = market.get("question") or market.get("title")
        print(f"  [{index}] {question}")


async def main_async(limit: int, search: str | None, dump_json: str | None) -> None:
    setup_logging("INFO")
    events = await fetch_events(limit=limit, active_only=True)
    filtered = [event for event in events if _looks_interesting(_event_text(event)) and _matches_search(_event_text(event), search)]
    print(f"Active events fetched: {len(events)}")
    print(f"Interesting events: {len(filtered)}")
    print()

    if dump_json:
        path = Path(dump_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(filtered, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"Saved JSON dump: {path}")
        print()

    if not filtered:
        print("No matching events found.")
        return

    for event in filtered:
        print_event(event)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect Polymarket events for crypto short-market discovery.")
    parser.add_argument("--limit", type=int, default=200, help="Number of events to fetch")
    parser.add_argument("--search", type=str, default=None, help="Substring filter for event title")
    parser.add_argument("--dump-json", type=str, default=None, help="Save matching events to JSON file")
    args = parser.parse_args()
    asyncio.run(main_async(limit=args.limit, search=args.search, dump_json=args.dump_json))


if __name__ == "__main__":
    main()

