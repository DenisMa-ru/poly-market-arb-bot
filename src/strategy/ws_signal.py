from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass

from src.markets.updown_parser import UpDownMarket
from src.utils.logger import get_logger

try:
    import websockets
except ImportError:  # pragma: no cover - depends on runtime environment
    websockets = None

WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
logger = get_logger("src.strategy.ws_signal")


@dataclass(frozen=True)
class WsSignalConfig:
    runtime_seconds: int
    max_messages: int
    markets_limit: int
    take_profit: float
    stop_loss: float
    max_hold_seconds: int


class WsSignalRunner:
    def __init__(self, config: WsSignalConfig) -> None:
        self.config = config

    async def run(self, *, markets: list[UpDownMarket]) -> tuple[dict[str, object], list[dict[str, object]]]:
        if websockets is None:
            raise RuntimeError("websockets package is not installed")

        token_to_market = {market.up_token_id: market for market in markets[: self.config.markets_limit]}
        if not token_to_market:
            return {
                "messages": 0,
                "books": 0,
                "price_changes": 0,
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "avg_pnl": 0.0,
                "total_pnl": 0.0,
            }, []

        counts = {"messages": 0, "books": 0, "price_changes": 0}
        states: dict[str, dict[str, object]] = {}
        closed_trades: list[dict[str, object]] = []
        started = time.time()

        async with websockets.connect(WS_URL, ping_interval=20, ping_timeout=20) as ws:
            logger.info(
                "ws signal connect",
                extra={
                    "markets": len(token_to_market),
                    "runtime_seconds": self.config.runtime_seconds,
                    "max_messages": self.config.max_messages,
                },
            )
            await ws.send(json.dumps({"assets_ids": list(token_to_market.keys()), "type": "market"}))
            while counts["messages"] < self.config.max_messages and (time.time() - started) < self.config.runtime_seconds:
                raw = await asyncio.wait_for(ws.recv(), timeout=10)
                counts["messages"] += 1
                payload = json.loads(raw)
                events = payload if isinstance(payload, list) else [payload]
                now_ts = time.time()
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
                        state = states.setdefault(
                            market.slug,
                            {
                                "slug": market.slug,
                                "symbol": market.symbol,
                                "timeframe_minutes": market.timeframe_minutes,
                                "best_bid": best_bid,
                                "best_ask": best_ask,
                                "up_streak": 0,
                                "down_streak": 0,
                                "position": None,
                            },
                        )
                        state["best_bid"] = best_bid
                        state["best_ask"] = best_ask
                    elif event_type == "price_change":
                        counts["price_changes"] += 1
                        for change in event.get("price_changes", []):
                            if not isinstance(change, dict):
                                continue
                            asset_id = str(change.get("asset_id") or "")
                            market = token_to_market.get(asset_id)
                            if market is None:
                                continue
                            state = states.get(market.slug)
                            if state is None:
                                continue
                            best_bid = float(change.get("best_bid", state.get("best_bid") or 0.0)) if change.get("best_bid") is not None else state.get("best_bid")
                            best_ask = float(change.get("best_ask", state.get("best_ask") or 0.0)) if change.get("best_ask") is not None else state.get("best_ask")
                            state["best_bid"] = best_bid
                            state["best_ask"] = best_ask
                            side = str(change.get("side") or "").upper()
                            if side == "BUY":
                                state["up_streak"] = int(state.get("up_streak", 0)) + 1
                                state["down_streak"] = 0
                            elif side == "SELL":
                                state["down_streak"] = int(state.get("down_streak", 0)) + 1
                                state["up_streak"] = 0

                            position = state.get("position")
                            if position is None and state.get("up_streak", 0) >= 3 and best_ask is not None:
                                state["position"] = {
                                    "entry_price": float(best_ask),
                                    "entry_ts": now_ts,
                                    "entry_reason": "up_streak_3",
                                }
                                continue

                            if not isinstance(position, dict) or best_bid is None:
                                continue
                            entry_price = float(position["entry_price"])
                            pnl = round(float(best_bid) - entry_price, 4)
                            hold_seconds = now_ts - float(position["entry_ts"])
                            exit_reason = None
                            if pnl >= self.config.take_profit:
                                exit_reason = "take_profit"
                            elif pnl <= -self.config.stop_loss:
                                exit_reason = "stop_loss"
                            elif hold_seconds >= self.config.max_hold_seconds:
                                exit_reason = "max_hold"
                            if exit_reason is None:
                                continue
                            closed_trades.append(
                                {
                                    "slug": market.slug,
                                    "symbol": market.symbol,
                                    "timeframe_minutes": market.timeframe_minutes,
                                    "entry_price": entry_price,
                                    "exit_price": float(best_bid),
                                    "pnl": pnl,
                                    "hold_seconds": round(hold_seconds, 2),
                                    "entry_reason": position["entry_reason"],
                                    "exit_reason": exit_reason,
                                    "status": "win" if pnl > 0 else "loss" if pnl < 0 else "flat",
                                }
                            )
                            state["position"] = None
                            state["up_streak"] = 0
                            state["down_streak"] = 0

        trades = len(closed_trades)
        wins = sum(1 for trade in closed_trades if float(trade["pnl"]) > 0)
        losses = sum(1 for trade in closed_trades if float(trade["pnl"]) < 0)
        total_pnl = round(sum(float(trade["pnl"]) for trade in closed_trades), 4)
        summary = {
            "messages": counts["messages"],
            "books": counts["books"],
            "price_changes": counts["price_changes"],
            "trades": trades,
            "wins": wins,
            "losses": losses,
            "win_rate": round(wins / trades, 4) if trades else 0.0,
            "avg_pnl": round(total_pnl / trades, 4) if trades else 0.0,
            "total_pnl": total_pnl,
        }
        return summary, closed_trades[:20]
