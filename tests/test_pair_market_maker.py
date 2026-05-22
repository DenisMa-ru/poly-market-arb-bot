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
    mm = PairMarketMaker(PairMarketMakerConfig(enabled=True, markets_limit=5, target_pairs=1, min_paired_inventory=1, replenish_batch_size=1, max_free_inventory_per_side=10, quote_edge=0.01, skew_step=0.01, max_skew=3, reward_per_trade_usd=0.02))
    state = PairMarketMakerState(paired_inventory=1.0)
    result = mm.evaluate(_market(), _book(0.5, 0.51), _book(0.5, 0.51), state)
    assert result["sold_up"] or result["sold_down"]
    assert state.reward_pnl >= 0.02
    assert result["split_pairs"] == 0.0
    assert state.realized_pnl <= 0.02
    assert result["reward_pnl_delta"] >= 0.02


def test_pair_mm_completes_pair_when_pair_bid_above_par() -> None:
    mm = PairMarketMaker(PairMarketMakerConfig(enabled=True, markets_limit=5, target_pairs=1, min_paired_inventory=1, replenish_batch_size=1, max_free_inventory_per_side=10, quote_edge=0.01, skew_step=0.01, max_skew=3, reward_per_trade_usd=0.0))
    state = PairMarketMakerState(paired_inventory=1.0)
    result = mm.evaluate(_market(), _book(0.51, 0.52), _book(0.51, 0.52), state)
    assert result["pair_bid_sum"] == 1.02
    assert state.completed_pairs >= 1.0
    assert result["completed_pairs_delta"] == 1.0


def test_pair_mm_tracks_skew_mark_pnl_after_one_sided_sale() -> None:
    mm = PairMarketMaker(PairMarketMakerConfig(enabled=True, markets_limit=5, target_pairs=1, min_paired_inventory=1, replenish_batch_size=1, max_free_inventory_per_side=10, quote_edge=0.01, skew_step=0.0, max_skew=3, reward_per_trade_usd=0.0))
    state = PairMarketMakerState(paired_inventory=1.0)
    result = mm.evaluate(_market(), _book(0.5, 0.51), _book(0.45, 0.6), state)
    assert int(bool(result["sold_up"])) + int(bool(result["sold_down"])) == 1
    assert result["free_down_after"] >= 1.0 or result["free_up_after"] >= 1.0
    assert result["skew_mark_pnl"] != 0.0


def test_pair_mm_replenish_is_not_free() -> None:
    mm = PairMarketMaker(PairMarketMakerConfig(enabled=True, markets_limit=5, target_pairs=1, min_paired_inventory=1, replenish_batch_size=1, max_free_inventory_per_side=10, quote_edge=0.01, skew_step=0.01, max_skew=3, reward_per_trade_usd=0.0))
    state = PairMarketMakerState(paired_inventory=0.0)
    result = mm.evaluate(_market(), _book(0.5, 0.51), _book(0.45, 0.6), state)
    assert result["split_pairs"] == 1.0
    assert result["split_notional"] == 1.0
    assert result["split_notional_delta"] == 1.0
    assert state.split_notional == 1.0
    assert result["realized_pnl"] < 0.0


def test_pair_mm_allows_only_one_fill_side_per_scan() -> None:
    mm = PairMarketMaker(PairMarketMakerConfig(enabled=True, markets_limit=5, target_pairs=1, min_paired_inventory=1, replenish_batch_size=1, max_free_inventory_per_side=10, quote_edge=0.01, skew_step=0.01, max_skew=3, reward_per_trade_usd=0.0))
    state = PairMarketMakerState(paired_inventory=1.0)
    result = mm.evaluate(_market(), _book(0.5, 0.51), _book(0.5, 0.51), state)
    assert int(bool(result["sold_up"])) + int(bool(result["sold_down"])) == 1


def test_pair_mm_does_not_replenish_above_min_threshold() -> None:
    mm = PairMarketMaker(PairMarketMakerConfig(enabled=True, markets_limit=5, target_pairs=5, min_paired_inventory=2, replenish_batch_size=1, max_free_inventory_per_side=10, quote_edge=0.01, skew_step=0.01, max_skew=3, reward_per_trade_usd=0.0))
    state = PairMarketMakerState(paired_inventory=5.0)
    result = mm.evaluate(_market(), _book(0.5, 0.51), _book(0.5, 0.51), state)
    assert result["split_pairs"] == 0.0


def test_pair_mm_replenishes_in_batches_only_below_min_threshold() -> None:
    mm = PairMarketMaker(PairMarketMakerConfig(enabled=True, markets_limit=5, target_pairs=5, min_paired_inventory=2, replenish_batch_size=1, max_free_inventory_per_side=10, quote_edge=0.01, skew_step=0.01, max_skew=3, reward_per_trade_usd=0.0))
    state = PairMarketMakerState(paired_inventory=0.0)
    first = mm.evaluate(_market(), _book(0.1, 0.9), _book(0.1, 0.9), state)
    assert first["split_pairs"] == 1.0
    assert first["paired_inventory_after"] == 1.0


def test_pair_mm_skips_replenish_when_free_inventory_is_too_large() -> None:
    mm = PairMarketMaker(PairMarketMakerConfig(enabled=True, markets_limit=5, target_pairs=5, min_paired_inventory=2, replenish_batch_size=1, max_free_inventory_per_side=1, quote_edge=0.01, skew_step=0.01, max_skew=3, reward_per_trade_usd=0.0))
    state = PairMarketMakerState(paired_inventory=1.0, free_down=1.0)
    result = mm.evaluate(_market(), _book(0.45, 0.6), _book(0.5, 0.51), state)
    assert result["split_pairs"] == 0.0


def test_pair_mm_does_not_replenish_in_same_scan_as_fresh_fill() -> None:
    mm = PairMarketMaker(PairMarketMakerConfig(enabled=True, markets_limit=5, target_pairs=5, min_paired_inventory=2, replenish_batch_size=1, max_free_inventory_per_side=10, quote_edge=0.01, skew_step=0.01, max_skew=3, reward_per_trade_usd=0.0))
    state = PairMarketMakerState(paired_inventory=2.0)
    result = mm.evaluate(_market(), _book(0.5, 0.51), _book(0.45, 0.6), state)
    assert result["sold_up"] or result["sold_down"]
    assert result["split_pairs"] == 0.0
    assert result["paired_inventory_after"] == 1.0


def test_pair_mm_skips_replenish_when_total_free_inventory_hits_threshold() -> None:
    mm = PairMarketMaker(PairMarketMakerConfig(enabled=True, markets_limit=5, target_pairs=5, min_paired_inventory=2, replenish_batch_size=1, max_free_inventory_per_side=2, quote_edge=0.01, skew_step=0.01, max_skew=3, reward_per_trade_usd=0.0))
    state = PairMarketMakerState(paired_inventory=1.0, free_up=1.0, free_down=1.0)
    result = mm.evaluate(_market(), _book(0.7, 0.8), _book(0.2, 0.8), state)
    assert result["split_pairs"] == 0.0


def test_pair_mm_skips_replenish_when_any_free_inventory_is_open() -> None:
    mm = PairMarketMaker(PairMarketMakerConfig(enabled=True, markets_limit=5, target_pairs=5, min_paired_inventory=2, replenish_batch_size=1, max_free_inventory_per_side=10, quote_edge=0.01, skew_step=0.01, max_skew=3, reward_per_trade_usd=0.0))
    state = PairMarketMakerState(paired_inventory=1.0, free_down=1.0)
    result = mm.evaluate(_market(), _book(0.2, 0.8), _book(0.2, 0.8), state)
    assert result["sold_up"] is False
    assert result["sold_down"] is True
    assert result["split_pairs"] == 0.0
    assert result["paired_inventory_after"] == 1.0
    assert result["free_down_after"] == 0.0


def test_pair_mm_does_not_replenish_above_target_when_min_exceeds_target() -> None:
    mm = PairMarketMaker(PairMarketMakerConfig(enabled=True, markets_limit=5, target_pairs=1, min_paired_inventory=2, replenish_batch_size=1, max_free_inventory_per_side=10, quote_edge=0.01, skew_step=0.01, max_skew=3, reward_per_trade_usd=0.0))
    state = PairMarketMakerState(paired_inventory=1.0)
    result = mm.evaluate(_market(), _book(0.2, 0.8), _book(0.2, 0.8), state)
    assert result["split_pairs"] == 0.0
    assert result["paired_inventory_after"] == 1.0


def test_pair_mm_blocks_repeat_sale_into_existing_free_down_inventory() -> None:
    mm = PairMarketMaker(PairMarketMakerConfig(enabled=True, markets_limit=5, target_pairs=5, min_paired_inventory=1, replenish_batch_size=1, max_free_inventory_per_side=10, quote_edge=0.01, skew_step=0.0, max_skew=3, reward_per_trade_usd=0.0))
    state = PairMarketMakerState(paired_inventory=1.0, free_down=1.0)
    result = mm.evaluate(_market(), _book(0.5, 0.51), _book(0.2, 0.8), state)
    assert result["sold_up"] is False


def test_pair_mm_blocks_repeat_sale_into_existing_free_up_inventory() -> None:
    mm = PairMarketMaker(PairMarketMakerConfig(enabled=True, markets_limit=5, target_pairs=5, min_paired_inventory=1, replenish_batch_size=1, max_free_inventory_per_side=10, quote_edge=0.01, skew_step=0.0, max_skew=3, reward_per_trade_usd=0.0))
    state = PairMarketMakerState(paired_inventory=1.0, free_up=1.0)
    result = mm.evaluate(_market(), _book(0.2, 0.8), _book(0.5, 0.51), state)
    assert result["sold_down"] is False


def test_pair_mm_unwinds_free_down_inventory() -> None:
    mm = PairMarketMaker(PairMarketMakerConfig(enabled=True, markets_limit=5, target_pairs=5, min_paired_inventory=1, replenish_batch_size=1, max_free_inventory_per_side=10, quote_edge=0.01, skew_step=0.0, max_skew=3, reward_per_trade_usd=0.0))
    state = PairMarketMakerState(paired_inventory=0.0, free_down=1.0)
    result = mm.evaluate(_market(), _book(0.2, 0.8), _book(0.5, 0.51), state)
    assert result["sold_down"] is True
    assert result["down_quote"] == 0.51
    assert result["free_down_after"] == 0.0
    assert result["paired_inventory_after"] == 0.0
    assert result["realized_pnl_delta"] == 0.51


def test_pair_mm_unwinds_free_up_inventory() -> None:
    mm = PairMarketMaker(PairMarketMakerConfig(enabled=True, markets_limit=5, target_pairs=5, min_paired_inventory=1, replenish_batch_size=1, max_free_inventory_per_side=10, quote_edge=0.01, skew_step=0.0, max_skew=3, reward_per_trade_usd=0.0))
    state = PairMarketMakerState(paired_inventory=0.0, free_up=1.0)
    result = mm.evaluate(_market(), _book(0.5, 0.51), _book(0.2, 0.8), state)
    assert result["sold_up"] is True
    assert result["up_quote"] == 0.51
    assert result["free_up_after"] == 0.0
    assert result["paired_inventory_after"] == 0.0
    assert result["realized_pnl_delta"] == 0.51


def test_pair_mm_requires_quote_to_be_near_visible_ask_for_fill() -> None:
    mm = PairMarketMaker(PairMarketMakerConfig(enabled=True, markets_limit=5, target_pairs=1, min_paired_inventory=1, replenish_batch_size=1, max_free_inventory_per_side=10, quote_edge=0.01, skew_step=0.0, max_skew=3, reward_per_trade_usd=0.0))
    state = PairMarketMakerState(paired_inventory=1.0)
    result = mm.evaluate(_market(), _book(0.5, 0.6), _book(0.2, 0.8), state)
    assert result["sold_up"] is False


def test_pair_mm_allows_fill_when_quote_is_close_to_visible_ask() -> None:
    mm = PairMarketMaker(PairMarketMakerConfig(enabled=True, markets_limit=5, target_pairs=1, min_paired_inventory=1, replenish_batch_size=1, max_free_inventory_per_side=10, quote_edge=0.01, skew_step=0.0, max_skew=3, reward_per_trade_usd=0.0))
    state = PairMarketMakerState(paired_inventory=1.0)
    result = mm.evaluate(_market(), _book(0.5, 0.52), _book(0.2, 0.8), state)
    assert result["sold_up"] is True


def test_pair_mm_respects_scan_level_fill_budget() -> None:
    mm = PairMarketMaker(PairMarketMakerConfig(enabled=True, markets_limit=5, target_pairs=1, min_paired_inventory=1, replenish_batch_size=1, max_free_inventory_per_side=10, quote_edge=0.01, skew_step=0.0, max_skew=3, reward_per_trade_usd=0.0))
    state = PairMarketMakerState(paired_inventory=1.0)
    result = mm.evaluate(_market(), _book(0.5, 0.51), _book(0.2, 0.8), state, remaining_fill_budget=0)
    assert result["sold_up"] is False
    assert result["sold_down"] is False
    assert result["paired_inventory_after"] == 1.0


def test_pair_mm_adds_reward_bps_on_trade_notional() -> None:
    mm = PairMarketMaker(PairMarketMakerConfig(enabled=True, markets_limit=5, target_pairs=1, min_paired_inventory=1, replenish_batch_size=1, max_free_inventory_per_side=10, quote_edge=0.01, skew_step=0.0, max_skew=3, reward_per_trade_usd=0.0, reward_bps_per_trade=20.0))
    state = PairMarketMakerState(paired_inventory=1.0)
    result = mm.evaluate(_market(), _book(0.5, 0.51), _book(0.2, 0.8), state)
    assert result["sold_up"] is True
    assert result["reward_pnl_delta"] == 0.001


def test_pair_mm_counts_repaired_free_inventory_as_completed_pairs() -> None:
    mm = PairMarketMaker(PairMarketMakerConfig(enabled=True, markets_limit=5, target_pairs=5, min_paired_inventory=0, replenish_batch_size=1, max_free_inventory_per_side=10, quote_edge=0.01, skew_step=0.0, max_skew=3, reward_per_trade_usd=0.0))
    state = PairMarketMakerState(paired_inventory=0.0, free_up=1.0, free_down=1.0)
    result = mm.evaluate(_market(), _book(0.2, 0.8), _book(0.2, 0.8), state, remaining_fill_budget=0)
    assert result["completed_pairs_delta"] == 1.0
    assert result["paired_inventory_after"] == 1.0
    assert result["free_up_after"] == 0.0
    assert result["free_down_after"] == 0.0
    assert result["realized_pnl_delta"] == 0.0
