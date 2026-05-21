from __future__ import annotations

from dataclasses import dataclass

from src.analysis.slippage_estimator import walk_asks
from src.clients.base import Orderbook, Outcome, Side
from src.markets.market_parser import ParsedCryptoMarket


@dataclass(frozen=True)
class OpportunityLeg:
    token_id: str
    outcome: Outcome
    side: Side
    price: float
    size: float


@dataclass(frozen=True)
class Opportunity:
    market_id: str
    question: str
    symbol: str
    expiry_at: str | None
    detected_at_ms: int
    legs: tuple[OpportunityLeg, OpportunityLeg]
    ask_yes: float
    ask_no: float
    avg_yes_price: float
    avg_no_price: float
    size_contracts: float
    gross_edge_usd: float
    slippage_usd: float
    gas_usd: float
    net_edge_usd: float
    edge_bps: int
    notional_usd: float


class ArbitrageAnalyzer:
    def __init__(self, *, min_edge_bps: int, max_position_usd: float, slippage_bps: float, gas_estimate_usd: float) -> None:
        self.min_edge_bps = min_edge_bps
        self.max_position_usd = max_position_usd
        self.slippage_bps = slippage_bps
        self.gas_estimate_usd = gas_estimate_usd

    def detect_bundle_opportunity(self, market: ParsedCryptoMarket, yes_book: Orderbook, no_book: Orderbook) -> Opportunity | None:
        if yes_book.best_ask is None or no_book.best_ask is None:
            return None
        per_leg_cap = self.max_position_usd / 2.0
        yes_fill = walk_asks(yes_book, max_notional_usd=per_leg_cap)
        no_fill = walk_asks(no_book, max_notional_usd=per_leg_cap)
        contracts = min(yes_fill.contracts, no_fill.contracts)
        if contracts <= 0:
            return None
        yes_avg = yes_fill.avg_price
        no_avg = no_fill.avg_price
        notional = (yes_avg + no_avg) * contracts
        if notional <= 0:
            return None
        payout = contracts
        gross_edge = payout - notional
        slippage_usd = notional * (self.slippage_bps / 10_000.0)
        net_edge = gross_edge - slippage_usd - self.gas_estimate_usd
        edge_bps = int(round((net_edge / notional) * 10_000))
        if edge_bps < self.min_edge_bps:
            return None
        return Opportunity(
            market_id=market.market_id,
            question=market.question,
            symbol=market.symbol,
            expiry_at=market.expiry_at,
            detected_at_ms=max(yes_book.fetched_at_ms, no_book.fetched_at_ms),
            legs=(
                OpportunityLeg(token_id=market.yes_token_id, outcome=Outcome.YES, side=Side.BUY, price=yes_avg, size=contracts),
                OpportunityLeg(token_id=market.no_token_id, outcome=Outcome.NO, side=Side.BUY, price=no_avg, size=contracts),
            ),
            ask_yes=yes_book.best_ask.price,
            ask_no=no_book.best_ask.price,
            avg_yes_price=yes_avg,
            avg_no_price=no_avg,
            size_contracts=contracts,
            gross_edge_usd=gross_edge,
            slippage_usd=slippage_usd,
            gas_usd=self.gas_estimate_usd,
            net_edge_usd=net_edge,
            edge_bps=edge_bps,
            notional_usd=notional,
        )

