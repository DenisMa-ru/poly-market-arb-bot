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

    @staticmethod
    def _should_open_mean_reversion(
        *,
        best_bid: float | None,
        best_ask: float | None,
        spread: float | None,
        up_streak: int,
        down_streak: int,
        take_profit: float,
    ) -> bool:
        if best_bid is None or best_ask is None or spread is None:
            return False
        if down_streak < 3 or up_streak != 0:
            return False
        if spread > 0.01:
            return False
        if float(best_bid) < 0.05 or float(best_ask) > 0.95:
            return False
        midpoint = (float(best_bid) + float(best_ask)) / 2
        if midpoint > 0.5:
            return False
        if (1.0 - float(best_ask)) < take_profit:
            return False
        return True

    @staticmethod
    def _resolve_exit_reason(*, pnl: float, hold_seconds: float, up_streak: int, config: WsSignalConfig) -> str | None:
        if pnl >= config.take_profit:
            return "take_profit"
        if pnl <= -config.stop_loss:
            return "stop_loss"
        if up_streak >= 2:
            return "bounce_faded"
        if hold_seconds >= config.max_hold_seconds:
            return "max_hold"
        return None

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

                            spread = None
                            if best_bid is not None and best_ask is not None:
                                spread = round(float(best_ask) - float(best_bid), 4)

                            position = state.get("position")
                            if (
                                position is None
                                and self._should_open_mean_reversion(
                                    best_bid=float(best_bid) if best_bid is not None else None,
                                    best_ask=float(best_ask) if best_ask is not None else None,
                                    spread=spread,
                                    up_streak=int(state.get("up_streak", 0)),
                                    down_streak=int(state.get("down_streak", 0)),
                                    take_profit=self.config.take_profit,
                                )
                            ):
                                state["position"] = {
                                    "entry_price": float(best_ask),
                                    "entry_ts": now_ts,
                                    "entry_reason": "down_streak_3_tight_spread_midpoint_reversion",
                                    "entry_best_bid": best_bid,
                                    "entry_best_ask": best_ask,
                                    "max_favorable_excursion": 0.0,
                                    "max_adverse_excursion": 0.0,
                                }
                                continue

                            if not isinstance(position, dict) or best_bid is None:
                                continue
                            entry_price = float(position["entry_price"])
                            pnl = round(float(best_bid) - entry_price, 4)
                            hold_seconds = now_ts - float(position["entry_ts"])
                            position["max_favorable_excursion"] = max(float(position.get("max_favorable_excursion", 0.0)), pnl)
                            position["max_adverse_excursion"] = min(float(position.get("max_adverse_excursion", 0.0)), pnl)
                            exit_reason = self._resolve_exit_reason(
                                pnl=pnl,
                                hold_seconds=hold_seconds,
                                up_streak=int(state.get("up_streak", 0)),
                                config=self.config,
                            )
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
                                    "entry_best_bid": position.get("entry_best_bid"),
                                    "entry_best_ask": position.get("entry_best_ask"),
                                    "exit_reason": exit_reason,
                                    "exit_best_bid": best_bid,
                                    "exit_best_ask": best_ask,
                                    "up_streak_at_exit": state.get("up_streak", 0),
                                    "down_streak_at_exit": state.get("down_streak", 0),
                                    "max_favorable_excursion": round(float(position.get("max_favorable_excursion", 0.0)), 4),
                                    "max_adverse_excursion": round(float(position.get("max_adverse_excursion", 0.0)), 4),
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
