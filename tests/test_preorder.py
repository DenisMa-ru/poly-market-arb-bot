from src.clients.base import Orderbook, OrderbookLevel, Outcome, Venue
from src.markets.updown_parser import UpDownMarket
from src.strategy.preorder import PreOrderConfig, PreOrderSimulator


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


def test_preorder_full_fill() -> None:
    sim = PreOrderSimulator(PreOrderConfig(enabled=True, target_price_up=0.49, target_price_down=0.49, max_bundle_cost=0.98, partial_exit_price=0.47))
    up_book = Orderbook(Venue.POLYMARKET, "up1", Outcome.YES, (), (OrderbookLevel(0.48, 100),), 1)
    down_book = Orderbook(Venue.POLYMARKET, "down1", Outcome.NO, (), (OrderbookLevel(0.48, 100),), 1)
    result = sim.evaluate(_market(), up_book, down_book)
    assert result.status == "full_fill"
    assert result.bundle_cost == 0.98
    assert result.best_ask_up == 0.48
    assert result.distance_up == -0.01


def test_preorder_partial_fill() -> None:
    sim = PreOrderSimulator(PreOrderConfig(enabled=True, target_price_up=0.49, target_price_down=0.49, max_bundle_cost=0.98, partial_exit_price=0.47))
    up_book = Orderbook(Venue.POLYMARKET, "up1", Outcome.YES, (), (OrderbookLevel(0.48, 100),), 1)
    down_book = Orderbook(Venue.POLYMARKET, "down1", Outcome.NO, (), (OrderbookLevel(0.50, 100),), 1)
    result = sim.evaluate(_market(), up_book, down_book)
    assert result.status == "partial_fill"
    assert result.missing_leg == "down"
    assert result.partial_exit_loss == 0.02


def test_preorder_no_fill() -> None:
    sim = PreOrderSimulator(PreOrderConfig(enabled=True, target_price_up=0.49, target_price_down=0.49, max_bundle_cost=0.98, partial_exit_price=0.47))
    up_book = Orderbook(Venue.POLYMARKET, "up1", Outcome.YES, (), (OrderbookLevel(0.50, 100),), 1)
    down_book = Orderbook(Venue.POLYMARKET, "down1", Outcome.NO, (), (OrderbookLevel(0.50, 100),), 1)
    result = sim.evaluate(_market(), up_book, down_book)
    assert result.status == "no_fill"
