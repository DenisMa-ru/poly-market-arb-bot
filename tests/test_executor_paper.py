from src.analysis.arbitrage_analyzer import Opportunity, OpportunityLeg
from src.clients.base import Outcome, Side
from src.execution.executor import Executor
from src.storage.db import Database


def test_executor_creates_trade_and_position(tmp_path) -> None:
    db = Database(tmp_path / "test.db")
    executor = Executor(db=db, max_open_exposure_usd=500, starting_balance_usd=1000)
    opportunity = Opportunity(
        market_id="m1",
        question="Will BTC be above $105,000 in 5 min?",
        symbol="BTC",
        expiry_at="2099-01-01T00:00:00Z",
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
    decision = executor.handle(opportunity)
    assert decision.accepted is True
    assert decision.trade_id is not None
    assert decision.position_id is not None
    assert len(db.recent_trades()) == 1
    assert len(db.open_positions()) == 1
    assert db.latest_balance() == 955.0

