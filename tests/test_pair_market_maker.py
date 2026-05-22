from src.clients.base import Orderbook, OrderbookLevel, Outcome, Venue
from src.markets.updown_parser import UpDownMarket
from src.strategy.pair_market_maker import PairMarketMaker, PairMarketMakerConfig, PairMarketMakerState


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


def _book(bid: float, ask: float) -> Orderbook:
    return Orderbook(Venue.POLYMARKET, "t1", Outcome.YES, (OrderbookLevel(bid, 100),), (OrderbookLevel(ask, 100),), 1)


def test_pair_mm_sells_inventory_and_collects_reward() -> None:
    mm = PairMarketMaker(PairMarketMakerConfig(enabled=True, markets_limit=5, target_pairs=1, quote_edge=0.01, skew_step=0.01, max_skew=3, reward_per_trade_usd=0.02))
    state = PairMarketMakerState(up_inventory=1.0, down_inventory=1.0)
    result = mm.evaluate(_market(), _book(0.5, 0.51), _book(0.5, 0.51), state)
    assert result["sold_up"] or result["sold_down"]
    assert state.reward_pnl >= 0.02


def test_pair_mm_completes_pair_when_pair_bid_above_par() -> None:
    mm = PairMarketMaker(PairMarketMakerConfig(enabled=True, markets_limit=5, target_pairs=1, quote_edge=0.01, skew_step=0.01, max_skew=3, reward_per_trade_usd=0.0))
    state = PairMarketMakerState(up_inventory=1.0, down_inventory=1.0)
    result = mm.evaluate(_market(), _book(0.51, 0.52), _book(0.51, 0.52), state)
    assert result["pair_bid_sum"] == 1.02
    assert state.completed_pairs >= 1.0
