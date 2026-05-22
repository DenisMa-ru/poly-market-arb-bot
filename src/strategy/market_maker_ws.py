from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass

from src.utils.logger import get_logger

try:
    import websockets
except ImportError:  # pragma: no cover - depends on runtime environment
    websockets = None

from src.markets.updown_parser import UpDownMarket
from src.strategy.market_maker import MarketMaker, MarketMakerFillResult, MarketMakerState

WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
logger = get_logger("src.strategy.market_maker_ws")


@dataclass(frozen=True)
class WsMarketMakerSummary:
    messages: int
    books: int
    price_changes: int
    quoted_markets: int
    fills: int
    bid_fills: int
    ask_fills: int
    realized_spread_capture: float
    unrealized_pnl: float
    net_inventory: float
    avg_bid_to_best_ask: float
    avg_ask_to_best_bid: float
    near_touch_bid_count: int
    near_touch_ask_count: int
    crossed_bid_count: int
    crossed_ask_count: int
    execution_bid_count: int
    execution_ask_count: int
    entry_quotes_posted: int
    exit_quotes_posted: int
    inventory_reduction_events: int


class WsMarketMakerRunner:
    def __init__(self, *, mm: MarketMaker, states: dict[str, MarketMakerState]) -> None:
        self.mm = mm
        self.states = states

    async def run(
        self,
        *,
        markets: list[UpDownMarket],
        runtime_seconds: int,
        max_messages: int,
    ) -> tuple[dict[str, object], list[dict[str, object]]]:
        if websockets is None:
            raise RuntimeError("websockets package is not installed")

        token_to_market = {market.up_token_id: market for market in markets[: self.mm.config.markets_limit]}
        if not token_to_market:
            return {
                "messages": 0,
                "books": 0,
                "price_changes": 0,
                "quoted_markets": 0,
                "fills": 0,
                "bid_fills": 0,
                "ask_fills": 0,
                "realized_spread_capture": 0.0,
                "unrealized_pnl": 0.0,
                "net_inventory": 0.0,
                "avg_bid_to_best_ask": 0.0,
                "avg_ask_to_best_bid": 0.0,
                "near_touch_bid_count": 0,
                "near_touch_ask_count": 0,
                "crossed_bid_count": 0,
                "crossed_ask_count": 0,
                "execution_bid_count": 0,
                "execution_ask_count": 0,
                "entry_quotes_posted": 0,
                "exit_quotes_posted": 0,
                "inventory_reduction_events": 0,
            }, []

        results: dict[str, dict[str, object]] = {}
        counts = {"messages": 0, "books": 0, "price_changes": 0}
        metrics = {
            "bid_to_best_ask": [],
            "ask_to_best_bid": [],
            "near_touch_bid_count": 0,
            "near_touch_ask_count": 0,
            "crossed_bid_count": 0,
            "crossed_ask_count": 0,
            "execution_bid_count": 0,
            "execution_ask_count": 0,
            "entry_quotes_posted": 0,
            "exit_quotes_posted": 0,
            "inventory_reduction_events": 0,
        }
        started = time.time()

        async with websockets.connect(WS_URL, ping_interval=20, ping_timeout=20) as ws:
            logger.info(
                "mm ws connect",
                extra={
                    "markets": len(token_to_market),
                    "runtime_seconds": runtime_seconds,
                    "max_messages": max_messages,
                },
            )
            await ws.send(json.dumps({"assets_ids": list(token_to_market.keys()), "type": "market"}))
            while counts["messages"] < max_messages and (time.time() - started) < runtime_seconds:
                raw = await asyncio.wait_for(ws.recv(), timeout=10)
                counts["messages"] += 1
                payload = json.loads(raw)
                events = payload if isinstance(payload, list) else [payload]
                for event in events:
                    if not isinstance(event, dict):
                        continue
                    event_type = event.get("event_type")
                    if event_type == "book":
                        counts["books"] += 1
                        asset_id = str(event.get("asset_id") or "")
                        market = token_to_market.get(asset_id)
                        if market is None:
                            continue
                        bids = event.get("bids") if isinstance(event.get("bids"), list) else []
                        asks = event.get("asks") if isinstance(event.get("asks"), list) else []
                        best_bid = max((float(level.get("price", 0.0)) for level in bids if isinstance(level, dict)), default=None)
                        best_ask = min((float(level.get("price", 999.0)) for level in asks if isinstance(level, dict)), default=None)
                        if best_ask == 999.0:
                            best_ask = None
                        state = self.states.setdefault(market.slug, MarketMakerState())
                        quote = self.mm.build_quote(best_bid=best_bid, best_ask=best_ask, inventory=state.inventory)
                        if quote is None:
                            continue
                        is_new_bid = state.active_bid != quote.bid
                        is_new_ask = state.active_ask != quote.ask
                        state.active_bid = quote.bid
                        state.active_ask = quote.ask
                        if is_new_bid:
                            state.bid_filled = False
                        if is_new_ask:
                            state.ask_filled = False
                        results[market.slug] = {
                            "slug": market.slug,
                            "symbol": market.symbol,
                            "timeframe_minutes": market.timeframe_minutes,
                            "bid": quote.bid,
                            "ask": quote.ask,
                            "best_bid": best_bid,
                            "best_ask": best_ask,
                            "inventory_before": state.inventory,
                            "inventory_after": state.inventory,
                            "filled_bid": False,
                            "filled_ask": False,
                            "spread_capture": 0.0,
                            "unrealized_pnl": 0.0,
                            "realized_pnl": state.realized_pnl,
                            "bid_to_best_ask": None if best_ask is None else round(best_ask - quote.bid, 4),
                            "ask_to_best_bid": None if best_bid is None else round(quote.ask - best_bid, 4),
                            "crossed_bid": False,
                            "crossed_ask": False,
                            "near_touch_bid": False,
                            "near_touch_ask": False,
                            "inventory_regime": quote.inventory_regime,
                            "exit_pressure": quote.exit_pressure,
                            "status": "quoted_ws",
                        }
                        metrics["entry_quotes_posted"] += 1 if state.inventory <= 0 else 0
                        metrics["exit_quotes_posted"] += 1 if state.inventory > 0 else 0
                    elif event_type == "price_change":
                        counts["price_changes"] += 1
                        for change in event.get("price_changes", []):
                            if not isinstance(change, dict):
                                continue
                            asset_id = str(change.get("asset_id") or "")
                            market = token_to_market.get(asset_id)
                            if market is None:
                                continue
                            current = results.get(market.slug)
                            if current is None:
                                continue
                            state = self.states.setdefault(market.slug, MarketMakerState())
                            best_bid = float(change.get("best_bid", current.get("best_bid") or 0.0)) if change.get("best_bid") is not None else current.get("best_bid")
                            best_ask = float(change.get("best_ask", current.get("best_ask") or 0.0)) if change.get("best_ask") is not None else current.get("best_ask")
                            side = str(change.get("side") or "")
                            bid_to_best_ask = None if current.get("bid") is None or best_ask is None else round(float(best_ask) - float(current["bid"]), 4)
                            ask_to_best_bid = None if current.get("ask") is None or best_bid is None else round(float(current["ask"]) - float(best_bid), 4)
                            crossed_bid = bool(bid_to_best_ask is not None and bid_to_best_ask <= 0)
                            crossed_ask = bool(ask_to_best_bid is not None and ask_to_best_bid <= 0)
                            near_touch_bid = bool(bid_to_best_ask is not None and 0 < bid_to_best_ask <= 0.01)
                            near_touch_ask = bool(ask_to_best_bid is not None and 0 < ask_to_best_bid <= 0.01)
                            filled_bid = bool(crossed_bid and not state.bid_filled)
                            sell_size = min(self.mm.config.order_size, state.inventory)
                            filled_ask = bool(crossed_ask and sell_size > 0 and not state.ask_filled)
                            spread_capture = 0.0
                            if filled_bid:
                                fill_price = float(current["bid"])
                                new_inventory = state.inventory + self.mm.config.order_size
                                total_cost = (state.avg_entry_price * state.inventory) + (fill_price * self.mm.config.order_size)
                                state.inventory = new_inventory
                                state.avg_entry_price = total_cost / new_inventory if new_inventory > 0 else 0.0
                                state.bid_filled = True
                                metrics["execution_bid_count"] += 1
                            if filled_ask:
                                spread_capture = round((float(current["ask"]) - state.avg_entry_price) * sell_size, 4)
                                state.realized_pnl = round(state.realized_pnl + spread_capture, 4)
                                state.inventory = round(state.inventory - sell_size, 4)
                                if state.inventory <= 0:
                                    state.inventory = 0.0
                                    state.avg_entry_price = 0.0
                                state.ask_filled = True
                                metrics["execution_ask_count"] += 1
                                metrics["inventory_reduction_events"] += 1
                            if bid_to_best_ask is not None:
                                metrics["bid_to_best_ask"].append(bid_to_best_ask)
                            if ask_to_best_bid is not None:
                                metrics["ask_to_best_bid"].append(ask_to_best_bid)
                            metrics["near_touch_bid_count"] += 1 if near_touch_bid else 0
                            metrics["near_touch_ask_count"] += 1 if near_touch_ask else 0
                            metrics["crossed_bid_count"] += 1 if crossed_bid else 0
                            metrics["crossed_ask_count"] += 1 if crossed_ask else 0
                            unrealized = round(((best_bid or 0.0) - state.avg_entry_price) * state.inventory, 4) if state.inventory > 0 and best_bid is not None else 0.0
                            current.update(
                                {
                                    "best_bid": best_bid,
                                    "best_ask": best_ask,
                                    "inventory_after": state.inventory,
                                    "filled_bid": bool(current.get("filled_bid")) or filled_bid,
                                    "filled_ask": bool(current.get("filled_ask")) or filled_ask,
                                    "spread_capture": round(float(current.get("spread_capture", 0.0)) + spread_capture, 4),
                                    "unrealized_pnl": unrealized,
                                    "realized_pnl": state.realized_pnl,
                                    "bid_to_best_ask": bid_to_best_ask,
                                    "ask_to_best_bid": ask_to_best_bid,
                                    "crossed_bid": crossed_bid,
                                    "crossed_ask": crossed_ask,
                                    "near_touch_bid": near_touch_bid,
                                    "near_touch_ask": near_touch_ask,
                                    "inventory_regime": current.get("inventory_regime"),
                                    "exit_pressure": current.get("exit_pressure"),
                                    "status": "fill_ws" if filled_bid or filled_ask else f"price_change_{side.lower()}",
                                }
                            )

        rows = list(results.values())
        summary = {
            "messages": counts["messages"],
            "books": counts["books"],
            "price_changes": counts["price_changes"],
            "quoted_markets": len(rows),
            "fills": sum(1 for row in rows if row.get("filled_bid") or row.get("filled_ask")),
            "bid_fills": sum(1 for row in rows if row.get("filled_bid")),
            "ask_fills": sum(1 for row in rows if row.get("filled_ask")),
            "realized_spread_capture": round(sum(float(row.get("spread_capture", 0.0)) for row in rows), 4),
            "unrealized_pnl": round(sum(float(row.get("unrealized_pnl", 0.0)) for row in rows), 4),
            "net_inventory": round(sum(float(row.get("inventory_after", 0.0)) for row in rows), 4),
            "avg_bid_to_best_ask": round(sum(metrics["bid_to_best_ask"]) / len(metrics["bid_to_best_ask"]), 4) if metrics["bid_to_best_ask"] else 0.0,
            "avg_ask_to_best_bid": round(sum(metrics["ask_to_best_bid"]) / len(metrics["ask_to_best_bid"]), 4) if metrics["ask_to_best_bid"] else 0.0,
            "near_touch_bid_count": metrics["near_touch_bid_count"],
            "near_touch_ask_count": metrics["near_touch_ask_count"],
            "crossed_bid_count": metrics["crossed_bid_count"],
            "crossed_ask_count": metrics["crossed_ask_count"],
            "execution_bid_count": metrics["execution_bid_count"],
            "execution_ask_count": metrics["execution_ask_count"],
            "entry_quotes_posted": metrics["entry_quotes_posted"],
            "exit_quotes_posted": metrics["exit_quotes_posted"],
            "inventory_reduction_events": metrics["inventory_reduction_events"],
        }
        return summary, rows[:20]
