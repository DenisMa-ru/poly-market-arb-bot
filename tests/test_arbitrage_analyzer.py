from src.analysis.arbitrage_analyzer import ArbitrageAnalyzer
from src.clients.base import Orderbook, OrderbookLevel, Outcome, Venue
from src.markets.market_parser import ParsedCryptoMarket


def test_detect_bundle_opportunity_positive_case() -> None:
    analyzer = ArbitrageAnalyzer(min_edge_bps=30, max_position_usd=100, slippage_bps=5, gas_estimate_usd=0.01)
    market = ParsedCryptoMarket(
        market_id="m1",
        question="Will BTC be above $105,000 in 5 min?",
        symbol="BTC",
        timeframe_minutes=5,
        strike=105000.0,
        expiry_at="2026-05-21T15:00:00Z",
        yes_token_id="yes1",
        no_token_id="no1",
        raw_market=None,  # type: ignore[arg-type]
    )
    yes_book = Orderbook(
        venue=Venue.POLYMARKET,
        market_id="yes1",
        outcome=Outcome.YES,
        bids=(),
        asks=(OrderbookLevel(0.45, 200),),
        fetched_at_ms=1,
    )
    no_book = Orderbook(
        venue=Venue.POLYMARKET,
        market_id="no1",
        outcome=Outcome.NO,
        bids=(),
        asks=(OrderbookLevel(0.45, 200),),
        fetched_at_ms=2,
    )
    opportunity = analyzer.detect_bundle_opportunity(market, yes_book, no_book)
    assert opportunity is not None
    assert opportunity.edge_bps > 30
    assert opportunity.size_contracts > 0


def test_detect_bundle_opportunity_negative_case() -> None:
    analyzer = ArbitrageAnalyzer(min_edge_bps=30, max_position_usd=100, slippage_bps=5, gas_estimate_usd=0.01)
    market = ParsedCryptoMarket(
        market_id="m1",
        question="Will BTC be above $105,000 in 5 min?",
        symbol="BTC",
        timeframe_minutes=5,
        strike=105000.0,
        expiry_at="2026-05-21T15:00:00Z",
        yes_token_id="yes1",
        no_token_id="no1",
        raw_market=None,  # type: ignore[arg-type]
    )
    yes_book = Orderbook(Venue.POLYMARKET, "yes1", Outcome.YES, (), (OrderbookLevel(0.50, 200),), 1)
    no_book = Orderbook(Venue.POLYMARKET, "no1", Outcome.NO, (), (OrderbookLevel(0.50, 200),), 2)
    assert analyzer.detect_bundle_opportunity(market, yes_book, no_book) is None

