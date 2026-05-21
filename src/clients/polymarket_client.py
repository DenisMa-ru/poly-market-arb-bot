from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import httpx
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, BalanceAllowanceParams, MarketOrderArgs, OrderType

from src.clients.base import BaseExchangeClient, Market, OrderRequest, OrderResult, Orderbook, OrderbookLevel, Outcome, Side, Venue
from src.utils.retry import retry_api_call

logger = logging.getLogger(__name__)
GAMMA_BASE = "https://gamma-api.polymarket.com"


class PolymarketClient(BaseExchangeClient):
    venue = Venue.POLYMARKET

    def __init__(self, *, private_key: str, host: str, chain_id: int, signature_type: int, funder: str | None, gamma_base: str = GAMMA_BASE) -> None:
        self._clob = ClobClient(
            host=host,
            chain_id=chain_id,
            key=private_key,
            signature_type=signature_type if signature_type != 0 else None,
            funder=funder or None,
        )
        self._gamma = httpx.AsyncClient(base_url=gamma_base, timeout=15.0)
        self._creds_ready = False

    async def _ensure_creds(self) -> None:
        if self._creds_ready:
            return
        creds: ApiCreds = await asyncio.to_thread(self._clob.create_or_derive_api_creds)
        self._clob.set_api_creds(creds)
        self._creds_ready = True

    @retry_api_call
    async def list_markets(self, *, active_only: bool = True) -> list[Market]:
        params: dict[str, Any] = {"limit": 500, "offset": 0}
        if active_only:
            params["active"] = "true"
            params["closed"] = "false"
        out: list[Market] = []
        while True:
            response = await self._gamma.get("/markets", params=params)
            response.raise_for_status()
            page = response.json()
            if not page:
                break
            for raw in page:
                market = self._parse_gamma_market(raw)
                if market is not None:
                    out.append(market)
            if len(page) < params["limit"]:
                break
            params["offset"] += params["limit"]
            if params["offset"] >= 5000:
                break
        return out

    @retry_api_call
    async def get_event_by_slug(self, slug: str) -> dict[str, Any] | None:
        response = await self._gamma.get(f"/events/slug/{slug}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else None

    @staticmethod
    def _parse_gamma_market(raw: dict[str, Any]) -> Market | None:
        question = raw.get("question") or raw.get("title")
        if not question:
            return None
        tokens_raw = raw.get("clobTokenIds") or raw.get("tokens") or "[]"
        token_ids: list[str] = []
        if isinstance(tokens_raw, str):
            try:
                token_ids = list(json.loads(tokens_raw))
            except json.JSONDecodeError:
                token_ids = []
        elif isinstance(tokens_raw, list):
            token_ids = [str(t) for t in tokens_raw]
        outcomes_raw = raw.get("outcomes") or '["Yes", "No"]'
        outcomes: tuple[str, ...] = ("Yes", "No")
        if isinstance(outcomes_raw, str):
            try:
                parsed = json.loads(outcomes_raw)
                if isinstance(parsed, list):
                    outcomes = tuple(str(o) for o in parsed)
            except json.JSONDecodeError:
                pass
        return Market(
            venue=Venue.POLYMARKET,
            market_id=str(raw.get("conditionId") or raw.get("id") or raw.get("slug") or ""),
            question=str(question),
            outcomes=outcomes,
            yes_token_id=token_ids[0] if len(token_ids) >= 1 else None,
            no_token_id=token_ids[1] if len(token_ids) >= 2 else None,
            closes_at_iso=raw.get("endDate"),
            category=raw.get("category"),
            raw=raw,
        )

    async def get_orderbook(self, market_id: str, outcome: Outcome) -> Orderbook:
        book = await asyncio.to_thread(self._clob.get_order_book, market_id)
        bids = tuple(OrderbookLevel(price=float(b.price), size=float(b.size)) for b in sorted(book.bids, key=lambda x: -float(x.price)))
        asks = tuple(OrderbookLevel(price=float(a.price), size=float(a.size)) for a in sorted(book.asks, key=lambda x: float(x.price)))
        return Orderbook(venue=Venue.POLYMARKET, market_id=market_id, outcome=outcome, bids=bids, asks=asks, fetched_at_ms=int(time.time() * 1000))

    async def get_balance_usd(self) -> float:
        await self._ensure_creds()
        balance = await asyncio.to_thread(self._clob.get_balance_allowance, BalanceAllowanceParams())
        raw = balance.get("balance") if isinstance(balance, dict) else None
        if raw is None:
            return 0.0
        try:
            return float(int(raw)) / 1_000_000
        except (TypeError, ValueError):
            return 0.0

    async def place_order(self, req: OrderRequest) -> OrderResult:
        await self._ensure_creds()
        side_str = "BUY" if req.side is Side.BUY else "SELL"
        args = MarketOrderArgs(token_id=req.market_id, amount=req.size if req.side is Side.SELL else req.size * req.price, side=side_str, price=req.price)
        signed = await asyncio.to_thread(self._clob.create_market_order, args)
        resp = await asyncio.to_thread(self._clob.post_order, signed, OrderType.FOK)
        success = bool(resp.get("success"))
        order_id = resp.get("orderID") or resp.get("order_id")
        return OrderResult(venue=Venue.POLYMARKET, venue_order_id=str(order_id) if order_id else None, accepted=success, filled_size=float(resp.get("makingAmount", req.size)) if success else 0.0, avg_fill_price=req.price, fee_usd=0.0, raw_response=resp, error=None if success else str(resp.get("errorMsg") or resp.get("error") or "rejected"))

    async def cancel_order(self, venue_order_id: str) -> bool:
        try:
            result = await asyncio.to_thread(self._clob.cancel_orders, [venue_order_id])
            return bool(result.get("canceled")) if isinstance(result, dict) else False
        except Exception as exc:
            logger.warning("polymarket cancel failed", extra={"error": str(exc)})
            return False

    async def close(self) -> None:
        await self._gamma.aclose()
