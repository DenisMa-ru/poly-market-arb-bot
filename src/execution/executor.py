from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.analysis.arbitrage_analyzer import Opportunity
from src.storage.db import Database


class ExecutionMode(str, Enum):
    PAPER = "paper"


@dataclass(frozen=True)
class ExecutionDecision:
    accepted: bool
    reason: str
    opportunity_id: int | None = None
    trade_id: int | None = None
    position_id: int | None = None


class Executor:
    def __init__(self, *, db: Database, max_open_exposure_usd: float, starting_balance_usd: float) -> None:
        self.db = db
        self.max_open_exposure_usd = max_open_exposure_usd
        self.starting_balance_usd = starting_balance_usd
        if self.db.latest_balance() is None:
            self.db.snapshot_balance(starting_balance_usd, note="initial")

    def handle(self, opportunity: Opportunity) -> ExecutionDecision:
        current_exposure = self.db.open_exposure_usd()
        if current_exposure + opportunity.notional_usd > self.max_open_exposure_usd:
            opportunity_id = self._persist_opportunity(opportunity, decision="rejected", decision_reason="open exposure limit")
            return ExecutionDecision(False, "open_exposure_limit", opportunity_id=opportunity_id)
        balance = self.db.latest_balance()
        if balance is not None and balance < opportunity.notional_usd:
            opportunity_id = self._persist_opportunity(opportunity, decision="rejected", decision_reason="insufficient paper balance")
            return ExecutionDecision(False, "insufficient_balance", opportunity_id=opportunity_id)
        opportunity_id = self._persist_opportunity(opportunity, decision="paper_traded", decision_reason=None)
        trade_id = self.db.insert_trade(opportunity_id, mode=ExecutionMode.PAPER.value, status="filled", expected_pnl=opportunity.net_edge_usd, notes="paper")
        for leg in opportunity.legs:
            self.db.insert_leg(
                trade_id=trade_id,
                token_id=leg.token_id,
                outcome=leg.outcome.value,
                requested_size=leg.size,
                requested_price=leg.price,
                filled_size=leg.size,
                avg_fill_price=leg.price,
                fee_usd=0.0,
                status="paper_filled",
            )
        position_id = self.db.insert_position(
            trade_id=trade_id,
            market_id=opportunity.market_id,
            question=opportunity.question,
            symbol=opportunity.symbol,
            expiry_at=opportunity.expiry_at,
            status="open",
            size_contracts=opportunity.size_contracts,
            invested_usd=opportunity.notional_usd,
            expected_payout_usd=opportunity.size_contracts,
            realized_pnl=None,
            resolved_at=None,
        )
        new_balance = (balance if balance is not None else self.starting_balance_usd) - opportunity.notional_usd
        self.db.snapshot_balance(new_balance, note=f"paper entry trade_id={trade_id}")
        return ExecutionDecision(True, "paper_filled", opportunity_id=opportunity_id, trade_id=trade_id, position_id=position_id)

    def _persist_opportunity(self, opportunity: Opportunity, *, decision: str, decision_reason: str | None) -> int:
        return self.db.insert_opportunity(
            market_id=opportunity.market_id,
            question=opportunity.question,
            symbol=opportunity.symbol,
            expiry_at=opportunity.expiry_at,
            ask_yes=opportunity.ask_yes,
            ask_no=opportunity.ask_no,
            avg_yes_price=opportunity.avg_yes_price,
            avg_no_price=opportunity.avg_no_price,
            size_contracts=opportunity.size_contracts,
            gross_edge_usd=opportunity.gross_edge_usd,
            slippage_usd=opportunity.slippage_usd,
            gas_usd=opportunity.gas_usd,
            net_edge_usd=opportunity.net_edge_usd,
            edge_bps=opportunity.edge_bps,
            notional_usd=opportunity.notional_usd,
            decision=decision,
            decision_reason=decision_reason,
        )
