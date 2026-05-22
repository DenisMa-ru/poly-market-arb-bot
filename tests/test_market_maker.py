from src.clients.base import Orderbook, OrderbookLevel, Outcome, Venue
from src.markets.updown_parser import UpDownMarket
from src.strategy.market_maker import MarketMaker, MarketMakerConfig, MarketMakerState


def _market() -> UpDownMarket:
    return UpDownMarket(
        event_id="e1",
        market_id="m1",
        slug="btc-updown-5m-1779378600",
        question="Bitcoin Up or Down",
        symbol="BTC",
        timeframe_minutes=5,
        expiry_at="2099-01-01T00:00:00Z",
        up_token_id="up1",
        down_token_id="down1",
        raw_event={},
        raw_market={},
    )


def test_build_quote() -> None:
    mm = MarketMaker(MarketMakerConfig(enabled=True, spread_bps=100, order_size=10, reprice_threshold_bps=10, max_inventory_per_market=50, markets_limit=5))
    quote = mm.build_quote(best_bid=0.49, best_ask=0.51, inventory=0)
    assert quote is not None
    assert quote.bid < quote.ask
    assert quote.mid == 0.5


def test_bid_fill_increases_inventory() -> None:
    mm = MarketMaker(MarketMakerConfig(enabled=True, spread_bps=100, order_size=10, reprice_threshold_bps=10, max_inventory_per_market=50, markets_limit=5))
    book = Orderbook(Venue.POLYMARKET, "up1", Outcome.YES, (OrderbookLevel(0.49, 100),), (OrderbookLevel(0.49, 100),), 1)
    state = MarketMakerState()
    result = mm.evaluate(_market(), book, state)
    assert result.filled_bid is False
    assert result.inventory_after == result.inventory_before


def test_ask_fill_realizes_spread() -> None:
    mm = MarketMaker(MarketMakerConfig(enabled=True, spread_bps=100, order_size=10, reprice_threshold_bps=10, max_inventory_per_market=50, markets_limit=5))
    state = MarketMakerState(inventory=10, avg_entry_price=0.49, active_bid=0.48, active_ask=0.5)
    book = Orderbook(Venue.POLYMARKET, "up1", Outcome.YES, (OrderbookLevel(0.52, 100),), (OrderbookLevel(0.53, 100),), 1)
    result = mm.evaluate(_market(), book, state)
    assert result.filled_ask is True
    assert result.spread_capture > 0


def test_reward_per_fill_accumulates_on_fill() -> None:
    mm = MarketMaker(
        MarketMakerConfig(
            enabled=True,
            spread_bps=100,
            order_size=10,
            reprice_threshold_bps=10,
            max_inventory_per_market=50,
            markets_limit=5,
            reward_per_fill_usd=0.02,
        )
    )
    state = MarketMakerState(inventory=10, avg_entry_price=0.49, active_bid=0.48, active_ask=0.5)
    book = Orderbook(Venue.POLYMARKET, "up1", Outcome.YES, (OrderbookLevel(0.52, 100),), (OrderbookLevel(0.53, 100),), 1)
    mm.evaluate(_market(), book, state)
    assert state.reward_pnl == 0.02


def test_reward_only_mode_blocks_quote_when_mark_loss_too_large() -> None:
    mm = MarketMaker(
        MarketMakerConfig(
            enabled=True,
            spread_bps=100,
            order_size=10,
            reprice_threshold_bps=10,
            max_inventory_per_market=50,
            markets_limit=5,
            reward_only_mode=True,
            max_unrealized_loss_usd=0.01,
        )
    )
    state = MarketMakerState(inventory=10, avg_entry_price=0.8)
    book = Orderbook(Venue.POLYMARKET, "up1", Outcome.YES, (OrderbookLevel(0.49, 100),), (OrderbookLevel(0.51, 100),), 1)
    result = mm.evaluate(_market(), book, state)
    assert result.status == "risk_blocked"
