from src.markets.updown_parser import parse_updown_event
from src.markets.updown_discovery import _build_candidate_slugs


def test_parse_updown_event_btc_5m() -> None:
    event = {
        "id": "1",
        "slug": "btc-updown-5m-1779378600",
        "title": "Bitcoin Up or Down - May 21, 11:50AM-11:55AM ET",
        "endDate": "2099-05-21T15:55:00Z",
        "markets": [
            {
                "question": "Bitcoin Up or Down - May 21, 11:50AM-11:55AM ET",
                "conditionId": "cond1",
                "endDate": "2099-05-21T15:55:00Z",
                "outcomes": '["Up", "Down"]',
                "clobTokenIds": '["up1", "down1"]',
            }
        ],
    }
    parsed = parse_updown_event(event)
    assert parsed is not None
    assert parsed.symbol == "BTC"
    assert parsed.timeframe_minutes == 5
    assert parsed.up_token_id == "up1"
    assert parsed.down_token_id == "down1"


def test_parse_updown_event_rejects_non_matching_slug() -> None:
    event = {"slug": "when-will-bitcoin-hit-150k", "markets": []}
    assert parse_updown_event(event) is None


def test_parse_updown_event_rejects_closed_market() -> None:
    event = {
        "id": "1",
        "slug": "btc-updown-5m-1779378600",
        "title": "Bitcoin Up or Down - May 21, 11:50AM-11:55AM ET",
        "active": False,
        "closed": True,
        "endDate": "2099-05-21T15:55:00Z",
        "markets": [
            {
                "question": "Bitcoin Up or Down - May 21, 11:50AM-11:55AM ET",
                "conditionId": "cond1",
                "endDate": "2099-05-21T15:55:00Z",
                "outcomes": '["Up", "Down"]',
                "clobTokenIds": '["up1", "down1"]',
            }
        ],
    }
    assert parse_updown_event(event) is None


def test_build_candidate_slugs_for_btc_eth() -> None:
    from datetime import UTC, datetime

    now = datetime(2026, 5, 21, 16, 13, 19, tzinfo=UTC)
    slugs = _build_candidate_slugs(["BTC", "ETH"], now=now)
    assert "btc-updown-5m-1779379800" in slugs
    assert "btc-updown-15m-1779379200" in slugs
    assert "eth-updown-5m-1779379800" in slugs
    assert "eth-updown-15m-1779379200" in slugs
