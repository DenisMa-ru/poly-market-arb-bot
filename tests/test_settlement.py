from datetime import datetime, timezone

from src.analysis.arbitrage_analyzer import Opportunity, OpportunityLeg
from src.clients.base import Outcome, Side
from src.execution.executor import Executor
from src.execution.settlement import SettlementEngine
from src.storage.db import Database


def test_settlement_resolves_expired_position(tmp_path) -> None:
    db = Database(tmp_path / "test.db")
    executor = Executor(db=db, max_open_exposure_usd=500, starting_balance_usd=1000)
    opportunity = Opportunity(
        market_id="m1",
        question="Will BTC be above $105,000 in 5 min?",
        symbol="BTC",
        expiry_at="2020-01-01T00:00:00Z",
        detected_at_ms=1,
        legs=(
            OpportunityLeg("yes1", Outcome.YES, Side.BUY, 0.45, 50),
            OpportunityLeg("no1", Outcome.NO, Side.BUY, 0.45, 50),
        ),
        ask_yes=0.45,
        ask_no=0.45,
        avg_yes_price=0.45,
        avg_no_price=0.45,
        size_contracts=50,
        gross_edge_usd=5.0,
        slippage_usd=0.02,
        gas_usd=0.01,
        net_edge_usd=4.97,
        edge_bps=552,
        notional_usd=45.0,
    )
    executor.handle(opportunity)
    settlement = SettlementEngine(db)
    settled = settlement.settle_expired_positions(now=datetime.now(timezone.utc))
    assert settled == 1
    assert len(db.open_positions()) == 0
    assert len(db.resolved_positions()) == 1
    assert db.realized_pnl_total() == 5.0
    assert db.latest_balance() == 1005.0

