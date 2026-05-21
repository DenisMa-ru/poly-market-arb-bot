from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.analysis.arbitrage_analyzer import ArbitrageAnalyzer
from src.clients.base import Outcome
from src.clients.polymarket_client import PolymarketClient
from src.config.settings import get_settings
from src.execution.executor import Executor
from src.execution.settlement import SettlementEngine
from src.markets.updown_discovery import discover_updown_markets
from src.markets.updown_parser import UpDownMarket
from src.storage.db import Database
from src.utils.logger import get_logger, setup_logging

logger = get_logger("scripts.runner")


@dataclass(frozen=True)
class ScanStats:
    discovered: int = 0
    processed: int = 0
    opportunities: int = 0
    executed: int = 0
    errors: int = 0


def build_client() -> PolymarketClient:
    settings = get_settings()
    settings.assert_polymarket_ready()
    return PolymarketClient(
        private_key=settings.polymarket_pk,
        host=settings.polymarket_host,
        chain_id=settings.polymarket_chain_id,
        signature_type=settings.polymarket_signature_type,
        funder=settings.polymarket_funder or None,
    )


async def scan_once(client: PolymarketClient, db: Database, analyzer: ArbitrageAnalyzer, executor: Executor) -> ScanStats:
    settings = get_settings()
    filtered = await discover_updown_markets(client, settings.normalized_symbols())
    stats = ScanStats(discovered=len(filtered))
    logged_no_opportunity = 0
    if filtered:
        logger.info(
            "discovered updown markets",
            extra={
                "count": len(filtered),
                "slugs": [market.slug for market in filtered[:10]],
            },
        )
    for market in filtered:
        try:
            yes_book, no_book = await asyncio.gather(
                client.get_orderbook(market.up_token_id, Outcome.YES),
                client.get_orderbook(market.down_token_id, Outcome.NO),
            )
            stats = ScanStats(
                discovered=stats.discovered,
                processed=stats.processed + 1,
                opportunities=stats.opportunities,
                executed=stats.executed,
                errors=stats.errors,
            )
            opportunity = _detect_updown_opportunity(analyzer, market, yes_book, no_book)
            if opportunity is None:
                if logged_no_opportunity < 5:
                    ask_up = yes_book.best_ask.price if yes_book.best_ask else None
                    ask_down = no_book.best_ask.price if no_book.best_ask else None
                    logger.info(
                        "no opportunity",
                        extra={
                            "slug": market.slug,
                            "symbol": market.symbol,
                            "timeframe_minutes": market.timeframe_minutes,
                            "ask_up": ask_up,
                            "ask_down": ask_down,
                            "sum_asks": None if ask_up is None or ask_down is None else ask_up + ask_down,
                            "up_asks": len(yes_book.asks),
                            "down_asks": len(no_book.asks),
                        },
                    )
                    logged_no_opportunity += 1
                continue
            logger.info(
                "opportunity detected",
                extra={
                    "symbol": market.symbol,
                    "timeframe_minutes": market.timeframe_minutes,
                    "slug": market.slug,
                    "ask_up": opportunity.ask_yes,
                    "ask_down": opportunity.ask_no,
                    "sum_asks": opportunity.ask_yes + opportunity.ask_no,
                    "edge_bps": opportunity.edge_bps,
                    "net_edge_usd": opportunity.net_edge_usd,
                },
            )
            decision = executor.handle(opportunity)
            stats = ScanStats(
                discovered=stats.discovered,
                processed=stats.processed,
                opportunities=stats.opportunities + 1,
                executed=stats.executed + (1 if decision.accepted else 0),
                errors=stats.errors,
            )
        except Exception as exc:
            logger.warning(
                "market scan failed",
                extra={
                    "market_id": market.market_id,
                    "slug": market.slug,
                    "up_token_id": market.up_token_id,
                    "down_token_id": market.down_token_id,
                    "err": str(exc),
                },
            )
            db.insert_event(
                "WARNING",
                "market scan failed",
                {
                    "market_id": market.market_id,
                    "slug": market.slug,
                    "up_token_id": market.up_token_id,
                    "down_token_id": market.down_token_id,
                    "err": str(exc),
                },
            )
            stats = ScanStats(
                discovered=stats.discovered,
                processed=stats.processed,
                opportunities=stats.opportunities,
                executed=stats.executed,
                errors=stats.errors + 1,
            )
    return stats


def _detect_updown_opportunity(analyzer: ArbitrageAnalyzer, market: UpDownMarket, yes_book, no_book):
    from src.markets.market_parser import ParsedCryptoMarket

    parsed = ParsedCryptoMarket(
        market_id=market.market_id,
        question=market.question,
        symbol=market.symbol,
        timeframe_minutes=market.timeframe_minutes,
        strike=None,
        expiry_at=market.expiry_at,
        yes_token_id=market.up_token_id,
        no_token_id=market.down_token_id,
        raw_market=None,  # type: ignore[arg-type]
    )
    return analyzer.detect_bundle_opportunity(parsed, yes_book, no_book)


async def run_loop() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    db = Database(settings.db_full_path)
    client = build_client()
    analyzer = ArbitrageAnalyzer(
        min_edge_bps=settings.min_edge_bps,
        max_position_usd=settings.max_position_usd,
        slippage_bps=settings.slippage_bps,
        gas_estimate_usd=settings.gas_estimate_usd,
    )
    executor = Executor(
        db=db,
        max_open_exposure_usd=settings.max_open_exposure_usd,
        starting_balance_usd=settings.paper_starting_balance_usd,
    )
    settlement = SettlementEngine(db)
    try:
        while True:
            started = time.time()
            try:
                stats = await scan_once(client, db, analyzer, executor)
                settled = settlement.settle_expired_positions()
                logger.info(
                    "scan complete",
                    extra={
                        "discovered": stats.discovered,
                        "processed": stats.processed,
                        "opportunities": stats.opportunities,
                        "executed": stats.executed,
                        "errors": stats.errors,
                        "settled": settled,
                        "elapsed_s": time.time() - started,
                    },
                )
            except asyncio.CancelledError:
                logger.info("shutdown requested")
                break
            except Exception as exc:
                logger.exception("scan failed")
                db.insert_event("ERROR", "scan failed", {"err": str(exc)})
            await asyncio.sleep(settings.scan_interval_seconds)
    finally:
        await client.close()
        db.close()
