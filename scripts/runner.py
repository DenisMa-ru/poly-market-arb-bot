from __future__ import annotations

import asyncio
import sys
import time
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
from src.markets.market_filter import filter_supported_markets
from src.storage.db import Database
from src.utils.logger import get_logger, setup_logging

logger = get_logger("scripts.runner")


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


async def scan_once(client: PolymarketClient, db: Database, analyzer: ArbitrageAnalyzer, executor: Executor) -> int:
    settings = get_settings()
    markets = await client.list_markets(active_only=True)
    filtered = filter_supported_markets(markets, set(settings.normalized_symbols()))
    found = 0
    for market in filtered:
        try:
            yes_book, no_book = await asyncio.gather(
                client.get_orderbook(market.yes_token_id, Outcome.YES),
                client.get_orderbook(market.no_token_id, Outcome.NO),
            )
            opportunity = analyzer.detect_bundle_opportunity(market, yes_book, no_book)
            if opportunity is None:
                continue
            executor.handle(opportunity)
            found += 1
        except Exception as exc:
            logger.warning("market scan failed", extra={"market_id": market.market_id, "err": str(exc)})
            db.insert_event("WARNING", "market scan failed", {"market_id": market.market_id, "err": str(exc)})
    return found


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
                found = await scan_once(client, db, analyzer, executor)
                settled = settlement.settle_expired_positions()
                logger.info("scan complete", extra={"found": found, "settled": settled, "elapsed_s": time.time() - started})
            except Exception as exc:
                logger.exception("scan failed")
                db.insert_event("ERROR", "scan failed", {"err": str(exc)})
            await asyncio.sleep(settings.scan_interval_seconds)
    finally:
        await client.close()
        db.close()
