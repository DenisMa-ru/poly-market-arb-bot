from src.clients.base import Market, Venue
from src.markets.market_parser import parse_crypto_market


def test_parse_btc_5m_market() -> None:
    market = Market(
        venue=Venue.POLYMARKET,
        market_id="m1",
        question="Will BTC be above $105,000 in 5 min?",
        outcomes=("Yes", "No"),
        yes_token_id="yes1",
        no_token_id="no1",
        closes_at_iso="2026-05-21T15:00:00Z",
    )
    parsed = parse_crypto_market(market)
    assert parsed is not None
    assert parsed.symbol == "BTC"
    assert parsed.timeframe_minutes == 5
    assert parsed.strike == 105000.0


def test_parse_rejects_market_without_tokens() -> None:
    market = Market(
        venue=Venue.POLYMARKET,
        market_id="m2",
        question="Will ETH be above $2,500 in 5 min?",
        outcomes=("Yes", "No"),
    )
    assert parse_crypto_market(market) is None


def test_parse_bitcoin_5m_short_format() -> None:
    market = Market(
        venue=Venue.POLYMARKET,
        market_id="m3",
        question="Will Bitcoin be over $105,000 in 5m?",
        outcomes=("Yes", "No"),
        yes_token_id="yes3",
        no_token_id="no3",
    )
    parsed = parse_crypto_market(market)
    assert parsed is not None
    assert parsed.symbol == "BTC"
    assert parsed.timeframe_minutes == 5
    assert parsed.strike == 105000.0


def test_parse_eth_15m_market_format() -> None:
    market = Market(
        venue=Venue.POLYMARKET,
        market_id="m4",
        question="Will Ethereum be above $2,500 in 15 minutes?",
        outcomes=("Yes", "No"),
        yes_token_id="yes4",
        no_token_id="no4",
    )
    parsed = parse_crypto_market(market)
    assert parsed is not None
    assert parsed.symbol == "ETH"
    assert parsed.timeframe_minutes == 15
    assert parsed.strike == 2500.0


def test_parse_rejects_non_short_btc_market() -> None:
    market = Market(
        venue=Venue.POLYMARKET,
        market_id="m5",
        question="Will bitcoin hit $1m before GTA VI?",
        outcomes=("Yes", "No"),
        yes_token_id="yes5",
        no_token_id="no5",
    )
    assert parse_crypto_market(market) is None


def test_parse_rejects_unsupported_timeframe() -> None:
    market = Market(
        venue=Venue.POLYMARKET,
        market_id="m6",
        question="Will BTC be above $105,000 in 1 min?",
        outcomes=("Yes", "No"),
        yes_token_id="yes6",
        no_token_id="no6",
    )
    assert parse_crypto_market(market) is None
