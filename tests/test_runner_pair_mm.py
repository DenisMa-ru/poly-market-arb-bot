from scripts.runner import _build_pair_mm_runner_for_scan, _build_pair_mm_skipped_row
from src.clients.base import Orderbook, OrderbookLevel, Outcome, Venue
from src.markets.updown_parser import UpDownMarket
from src.strategy.pair_market_maker import PairMarketMaker, PairMarketMakerConfig, PairMarketMakerState


def _market(slug: str) -> UpDownMarket:
    return UpDownMarket(
        event_id=f"e-{slug}",
        market_id=f"m-{slug}",
        slug=slug,
        question="Bitcoin Up or Down",
        symbol="BTC",
        timeframe_minutes=5,
        expiry_at="2099-01-01T00:00:00Z",
        up_token_id=f"up-{slug}",
        down_token_id=f"down-{slug}",
        raw_event={},
        raw_market={},
    )


def _book(bid: float, ask: float) -> Orderbook:
    return Orderbook(Venue.POLYMARKET, "t1", Outcome.YES, (OrderbookLevel(bid, 100),), (OrderbookLevel(ask, 100),), 1)


def test_clean_market_is_frozen_during_portfolio_unwind_mode() -> None:
    live_state = PairMarketMakerState(paired_inventory=2.0)
    result = _build_pair_mm_skipped_row(
        market=_market("btc-clean"),
        yes_book=_book(0.5, 0.51),
        no_book=_book(0.45, 0.6),
        state=live_state,
    )

    assert result["sold_up"] is False
    assert result["sold_down"] is False
    assert result["split_pairs"] == 0.0
    assert result["paired_inventory_after"] == 2.0
    assert live_state.paired_inventory == 2.0
    assert result["status"] == "skipped"


def test_replenish_budget_exhaustion_disables_scan_replenish() -> None:
    base_runner = PairMarketMaker(
        PairMarketMakerConfig(
            enabled=True,
            markets_limit=5,
            target_pairs=5,
            min_paired_inventory=2,
            replenish_batch_size=1,
            max_free_inventory_per_side=10,
            quote_edge=0.01,
            skew_step=0.01,
            max_skew=3,
            reward_per_trade_usd=0.0,
        )
    )

    limited_runner = _build_pair_mm_runner_for_scan(base_runner, replenish_blocked=True)

    assert limited_runner.config.min_paired_inventory == 0.0
    assert limited_runner.config.target_pairs == base_runner.config.target_pairs

    state = PairMarketMakerState(paired_inventory=0.0)
    result = limited_runner.evaluate(_market("btc-budget"), _book(0.2, 0.8), _book(0.2, 0.8), state)

    assert result["split_pairs"] == 0.0
    assert state.paired_inventory == 0.0
