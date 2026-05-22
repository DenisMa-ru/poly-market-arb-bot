from __future__ import annotations

from dataclasses import dataclass

from src.clients.base import Orderbook
from src.markets.updown_parser import UpDownMarket


@dataclass(frozen=True)
class MarketMakerConfig:
    enabled: bool
    spread_bps: float
    order_size: float
    reprice_threshold_bps: float
    max_inventory_per_market: float
    markets_limit: int


@dataclass(frozen=True)
class Quote:
    bid: float
    ask: float
    mid: float
    spread: float
    size: float
    skew_bps: float


@dataclass(frozen=True)
class MarketMakerFillResult:
    slug: str
    symbol: str
    timeframe_minutes: int
    bid: float | None
    ask: float | None
    best_bid: float | None
    best_ask: float | None
    filled_bid: bool
    filled_ask: bool
    inventory_before: float
    inventory_after: float
    quote_mid: float | None
    spread_capture: float
    unrealized_pnl: float
    realized_pnl: float
    replaces: int
    status: str


@dataclass
class MarketMakerState:
    inventory: float = 0.0
    avg_entry_price: float = 0.0
    active_bid: float | None = None
    active_ask: float | None = None
    bid_filled: bool = False
    ask_filled: bool = False
    quote_updates: int = 0
    fill_count: int = 0
    realized_pnl: float = 0.0


class MarketMaker:
    def __init__(self, config: MarketMakerConfig) -> None:
        self.config = config

    def build_quote(self, *, best_bid: float | None, best_ask: float | None, inventory: float) -> Quote | None:
        if best_bid is None or best_ask is None or best_bid > best_ask:
            return None
        mid = (best_bid + best_ask) / 2.0
        spread = max(mid * (self.config.spread_bps / 10_000.0), 0.01)
        skew_ratio = 0.0 if self.config.max_inventory_per_market <= 0 else max(min(inventory / self.config.max_inventory_per_market, 1.0), -1.0)
        bid_skew_bps = skew_ratio * self.config.spread_bps
        ask_skew_bps = skew_ratio * (self.config.spread_bps * 1.5)
        bid = max(0.01, mid - spread / 2.0 - mid * (bid_skew_bps / 10_000.0))
        ask = min(0.99, mid + spread / 2.0 - mid * (ask_skew_bps / 10_000.0))
        bid = round(bid, 2)
        ask = round(max(ask, bid + 0.01), 2)
        return Quote(bid=bid, ask=ask, mid=round(mid, 4), spread=round(ask - bid, 4), size=self.config.order_size, skew_bps=round(ask_skew_bps, 2))

    def evaluate(
        self,
        market: UpDownMarket,
        book: Orderbook,
        state: MarketMakerState,
    ) -> MarketMakerFillResult:
        best_bid = book.bids[0].price if book.bids else None
        best_ask = book.asks[0].price if book.asks else None
        inventory_before = state.inventory
        quote = self.build_quote(best_bid=best_bid, best_ask=best_ask, inventory=state.inventory)
        if quote is None:
            return MarketMakerFillResult(
                slug=market.slug,
                symbol=market.symbol,
                timeframe_minutes=market.timeframe_minutes,
                bid=None,
                ask=None,
                best_bid=best_bid,
                best_ask=best_ask,
                filled_bid=False,
                filled_ask=False,
                inventory_before=inventory_before,
                inventory_after=state.inventory,
                quote_mid=None,
                spread_capture=0.0,
                unrealized_pnl=0.0,
                realized_pnl=state.realized_pnl,
                replaces=0,
                status="skipped",
            )

        replaces = 0
        if state.active_bid is not None and abs(state.active_bid - quote.bid) >= 0.01:
            replaces += 1
        if state.active_ask is not None and abs(state.active_ask - quote.ask) >= 0.01:
            replaces += 1
        state.active_bid = quote.bid
        state.active_ask = quote.ask
        state.quote_updates += 1

        filled_bid = best_ask is not None and quote.bid >= best_ask
        filled_ask = best_bid is not None and quote.ask <= best_bid + 0.01 and state.inventory > 0

        spread_capture = 0.0
        if filled_bid:
            new_inventory = state.inventory + quote.size
            total_cost = (state.avg_entry_price * state.inventory) + (quote.bid * quote.size)
            state.inventory = new_inventory
            state.avg_entry_price = total_cost / new_inventory if new_inventory > 0 else 0.0
            state.fill_count += 1
        if filled_ask:
            sell_size = min(quote.size, state.inventory)
            spread_capture = round((quote.ask - state.avg_entry_price) * sell_size, 4)
            state.realized_pnl = round(state.realized_pnl + spread_capture, 4)
            state.inventory = round(state.inventory - sell_size, 4)
            if state.inventory <= 0:
                state.inventory = 0.0
                state.avg_entry_price = 0.0
            state.fill_count += 1

        mark_price = best_bid if state.inventory > 0 and best_bid is not None else quote.mid
        unrealized_pnl = round((mark_price - state.avg_entry_price) * state.inventory, 4) if state.inventory > 0 else 0.0
        status = "two_sided_fill" if filled_bid and filled_ask else "bid_fill" if filled_bid else "ask_fill" if filled_ask else "quoted"
        return MarketMakerFillResult(
            slug=market.slug,
            symbol=market.symbol,
            timeframe_minutes=market.timeframe_minutes,
            bid=quote.bid,
            ask=quote.ask,
            best_bid=best_bid,
            best_ask=best_ask,
            filled_bid=filled_bid,
            filled_ask=filled_ask,
            inventory_before=inventory_before,
            inventory_after=state.inventory,
            quote_mid=quote.mid,
            spread_capture=spread_capture,
            unrealized_pnl=unrealized_pnl,
            realized_pnl=state.realized_pnl,
            replaces=replaces,
            status=status,
        )
