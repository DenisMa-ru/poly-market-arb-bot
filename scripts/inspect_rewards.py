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

from src.utils.logger import setup_logging

REWARDS_BASE = "https://clob.polymarket.com"


def _as_float(value: object) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_text(value: object) -> str:
    return "" if value is None else str(value)


def _matches_search(item: dict[str, Any], search: str | None) -> bool:
    if not search:
        return True
    haystacks = [
        _as_text(item.get("question")),
        _as_text(item.get("market_slug")),
        _as_text(item.get("event_slug")),
        _as_text(item.get("tag_slug")),
    ]
    needle = search.upper()
    return any(needle in hay.upper() for hay in haystacks)


def _spread_bps(best_bid: float | None, best_ask: float | None) -> float | None:
    if best_bid is None or best_ask is None:
        return None
    mid = (best_bid + best_ask) / 2.0
    if mid <= 0:
        return None
    return ((best_ask - best_bid) / mid) * 10000.0


def _priority_score(item: dict[str, Any]) -> float:
    reward = _as_float(item.get("rate_per_day")) or 0.0
    volume = _as_float(item.get("volume_24hr")) or _as_float(item.get("volume24hr")) or _as_float(item.get("volume")) or 0.0
    spread_bps = _spread_bps(_as_float(item.get("best_bid")), _as_float(item.get("best_ask")))
    spread_penalty = spread_bps or 0.0
    return reward + (volume / 100000.0) - (spread_penalty / 10000.0)


async def fetch_reward_markets(
    *,
    limit: int,
    tag_slugs: list[str],
    search: str | None,
    sponsored: bool,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "limit": min(limit, 500),
        "sponsored": str(sponsored).lower(),
    }
    for tag in tag_slugs:
        params.setdefault("tag_slug", [])
        params["tag_slug"].append(tag)
    out: list[dict[str, Any]] = []
    cursor: str | None = None
    async with httpx.AsyncClient(base_url=REWARDS_BASE, timeout=20.0) as client:
        while len(out) < limit:
            request_params = dict(params)
            if cursor:
                request_params["next_cursor"] = cursor
            response = await client.get("/rewards/markets/multi", params=request_params)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                break
            items = payload.get("data") or payload.get("markets") or payload.get("results") or []
            if not isinstance(items, list) or not items:
                break
            for item in items:
                if isinstance(item, dict) and _matches_search(item, search):
                    out.append(item)
            cursor_raw = payload.get("next_cursor")
            cursor = str(cursor_raw) if cursor_raw else None
            if not cursor or cursor == "LTE=" or len(items) < request_params["limit"]:
                break
    return out[:limit]


def print_market(item: dict[str, Any]) -> None:
    best_bid = _as_float(item.get("best_bid"))
    best_ask = _as_float(item.get("best_ask"))
    print("=" * 100)
    print(f"question: {_as_text(item.get('question'))}")
    print(f"market_slug: {_as_text(item.get('market_slug'))}")
    print(f"event_slug: {_as_text(item.get('event_slug'))}")
    print(f"condition_id: {_as_text(item.get('condition_id'))}")
    print(f"tag_slug: {_as_text(item.get('tag_slug'))}")
    print(f"rate_per_day: {_as_float(item.get('rate_per_day'))}")
    print(f"rewards_max_spread: {_as_float(item.get('rewards_max_spread'))}")
    print(f"rewards_min_size: {_as_float(item.get('rewards_min_size'))}")
    print(f"best_bid: {best_bid}")
    print(f"best_ask: {best_ask}")
    print(f"spread_bps: {_spread_bps(best_bid, best_ask)}")
    print(f"volume_24hr: {_as_float(item.get('volume_24hr')) or _as_float(item.get('volume24hr'))}")
    print(f"priority_score: {_priority_score(item):.4f}")


async def main_async(limit: int, top: int, tag_slugs: list[str], search: str | None, dump_json: str | None, sponsored: bool) -> None:
    setup_logging("INFO")
    markets = await fetch_reward_markets(limit=limit, tag_slugs=tag_slugs, search=search, sponsored=sponsored)
    ranked = sorted(markets, key=_priority_score, reverse=True)

    print(f"Reward markets fetched: {len(markets)}")
    print(f"Sponsored folded in: {sponsored}")
    print(f"Tag filter: {tag_slugs or ['<none>']}")
    print()

    if dump_json:
        path = Path(dump_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(ranked, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"Saved JSON dump: {path}")
        print()

    if not ranked:
        print("No reward markets found.")
        return

    print("Top reward markets:")
    for item in ranked[:top]:
        print_market(item)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect Polymarket reward-eligible markets.")
    parser.add_argument("--limit", type=int, default=100, help="Maximum number of reward markets to fetch")
    parser.add_argument("--top", type=int, default=20, help="How many ranked markets to print")
    parser.add_argument("--tag", action="append", default=[], help="Repeatable tag filter, e.g. --tag sports --tag politics")
    parser.add_argument("--search", type=str, default=None, help="Substring filter for question/slug")
    parser.add_argument("--dump-json", type=str, default=None, help="Save fetched reward markets to JSON file")
    parser.add_argument("--no-sponsored", action="store_true", help="Do not fold sponsored daily rates into rate_per_day")
    args = parser.parse_args()
    asyncio.run(
        main_async(
            limit=args.limit,
            top=args.top,
            tag_slugs=list(args.tag),
            search=args.search,
            dump_json=args.dump_json,
            sponsored=not args.no_sponsored,
        )
    )


if __name__ == "__main__":
    main()
