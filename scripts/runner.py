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
from src.strategy.market_maker import MarketMaker, MarketMakerConfig, MarketMakerState
from src.strategy.market_maker_ws import WsMarketMakerRunner
from src.strategy.preorder import PreOrderConfig, PreOrderSimulator
from src.utils.logger import get_logger, setup_logging

logger = get_logger("scripts.runner")


@dataclass(frozen=True)
class ScanStats:
    discovered: int = 0
    processed: int = 0
    opportunities: int = 0
    executed: int = 0
    errors: int = 0


@dataclass(frozen=True)
class MarketSnapshot:
    slug: str
    symbol: str
    timeframe_minutes: int
    ask_up: float | None
    ask_down: float | None
    sum_asks: float | None
    up_asks: int
    down_asks: int


def _summarize_preorder_rows(rows: list[dict[str, object]]) -> dict[str, object]:
    full_fill = sum(1 for row in rows if row.get("status") == "full_fill")
    full_fill_over_budget = sum(1 for row in rows if row.get("status") == "full_fill_over_budget")
    partial_fill = sum(1 for row in rows if row.get("status") == "partial_fill")
    no_fill = sum(1 for row in rows if row.get("status") == "no_fill")
    partial_losses = [float(row["partial_exit_loss"]) for row in rows if row.get("partial_exit_loss") is not None]
    full_pnls = [float(row["expected_pnl"]) for row in rows if row.get("expected_pnl") is not None]
    return {
        "full_fill": full_fill,
        "full_fill_over_budget": full_fill_over_budget,
        "partial_fill": partial_fill,
        "no_fill": no_fill,
        "markets": len(rows),
        "full_fill_rate": round(full_fill / len(rows), 4) if rows else 0.0,
        "partial_fill_rate": round(partial_fill / len(rows), 4) if rows else 0.0,
        "avg_full_fill_pnl": round(sum(full_pnls) / len(full_pnls), 4) if full_pnls else None,
        "avg_partial_exit_loss": round(sum(partial_losses) / len(partial_losses), 4) if partial_losses else None,
        "worst_partial_exit_loss": round(max(partial_losses), 4) if partial_losses else None,
    }


def _summarize_mm_rows(rows: list[dict[str, object]]) -> dict[str, object]:
    fills = sum(1 for row in rows if row.get("filled_bid") or row.get("filled_ask"))
    bid_fills = sum(1 for row in rows if row.get("filled_bid"))
    ask_fills = sum(1 for row in rows if row.get("filled_ask"))
    replaces = sum(int(row.get("replaces", 0)) for row in rows)
    realized = round(sum(float(row.get("spread_capture", 0.0)) for row in rows), 4)
    unrealized_values = [float(row["unrealized_pnl"]) for row in rows if row.get("unrealized_pnl") is not None]
    inventories = [float(row["inventory_after"]) for row in rows if row.get("inventory_after") is not None]
    return {
        "markets": len(rows),
        "fills": fills,
        "bid_fills": bid_fills,
        "ask_fills": ask_fills,
        "fill_rate": round(fills / len(rows), 4) if rows else 0.0,
        "replaces": replaces,
        "realized_spread_capture": realized,
        "unrealized_pnl": round(sum(unrealized_values), 4) if unrealized_values else 0.0,
        "net_inventory": round(sum(inventories), 4) if inventories else 0.0,
        "max_inventory": round(max(inventories), 4) if inventories else 0.0,
    }


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
    snapshots: list[MarketSnapshot] = []
    preorder_results: list[dict[str, object]] = []
    mm_results: list[dict[str, object]] = []
    mm_ws_results: list[dict[str, object]] = []
    preorder = PreOrderSimulator(
        PreOrderConfig(
            enabled=settings.preorder_enabled,
            target_price_up=settings.preorder_target_price_up,
            target_price_down=settings.preorder_target_price_down,
            max_bundle_cost=settings.preorder_max_bundle_cost,
            partial_exit_price=settings.preorder_partial_exit_price,
        )
    )
    mm = MarketMaker(
        MarketMakerConfig(
            enabled=settings.mm_enabled,
            spread_bps=settings.mm_spread_bps,
            order_size=settings.mm_order_size,
            reprice_threshold_bps=settings.mm_reprice_threshold_bps,
            max_inventory_per_market=settings.mm_max_inventory_per_market,
            markets_limit=settings.mm_markets_limit,
        )
    )
    mm_states: dict[str, MarketMakerState] = getattr(scan_once, "_mm_states", {})
    setattr(scan_once, "_mm_states", mm_states)
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
            ask_up = yes_book.best_ask.price if yes_book.best_ask else None
            ask_down = no_book.best_ask.price if no_book.best_ask else None
            snapshots.append(
                MarketSnapshot(
                    slug=market.slug,
                    symbol=market.symbol,
                    timeframe_minutes=market.timeframe_minutes,
                    ask_up=ask_up,
                    ask_down=ask_down,
                    sum_asks=None if ask_up is None or ask_down is None else ask_up + ask_down,
                    up_asks=len(yes_book.asks),
                    down_asks=len(no_book.asks),
                )
            )
            if settings.preorder_enabled:
                preorder_result = preorder.evaluate(market, yes_book, no_book)
                preorder_results.append(preorder_result.__dict__)
            if settings.mm_enabled and len(mm_results) < settings.mm_markets_limit:
                state = mm_states.setdefault(market.slug, MarketMakerState())
                mm_result = mm.evaluate(market, yes_book, state)
                mm_results.append(mm_result.__dict__)
            opportunity = _detect_updown_opportunity(analyzer, market, yes_book, no_book)
            if opportunity is None:
                if logged_no_opportunity < 5:
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
    best_snapshots = sorted(
        (snapshot for snapshot in snapshots if snapshot.sum_asks is not None),
        key=lambda snapshot: snapshot.sum_asks,
    )[:10]
    db.insert_event(
        "INFO",
        "scan telemetry",
        {
            "discovered": stats.discovered,
            "processed": stats.processed,
            "opportunities": stats.opportunities,
            "executed": stats.executed,
            "errors": stats.errors,
            "best_markets": [snapshot.__dict__ for snapshot in best_snapshots],
        },
    )
    if best_snapshots:
        logger.info(
            "best near-arbs",
            extra={
                "markets": [snapshot.__dict__ for snapshot in best_snapshots[:5]],
            },
        )
    if settings.preorder_enabled:
        summary = _summarize_preorder_rows(preorder_results)
        best_candidates = sorted(
            preorder_results,
            key=lambda row: (
                row.get("status") not in {"full_fill", "full_fill_over_budget", "partial_fill"},
                max(
                    float(row["distance_up"]) if row.get("distance_up") is not None else 999.0,
                    float(row["distance_down"]) if row.get("distance_down") is not None else 999.0,
                ),
            ),
        )[:10]
        recent_events = db.recent_preorder_events(limit=50)
        rolling_rows: list[dict[str, object]] = []
        for event in recent_events:
            results = event.get("results")
            if isinstance(results, list):
                rolling_rows.extend(row for row in results if isinstance(row, dict))
        rolling_summary = _summarize_preorder_rows(rolling_rows)
        db.insert_event(
            "INFO",
            "preorder telemetry",
            {
                "summary": summary,
                "rolling_summary": rolling_summary,
                "best_candidates": best_candidates,
                "results": preorder_results[:20],
            },
        )
        logger.info("preorder summary", extra=summary)
    if settings.mm_enabled:
        mm_summary = _summarize_mm_rows(mm_results)
        db.insert_event("INFO", "mm telemetry", {"summary": mm_summary, "results": mm_results[:20]})
        logger.info("mm summary", extra=mm_summary)
        if settings.mm_ws_enabled:
            logger.info(
                "mm ws start",
                extra={
                    "markets_available": len(filtered),
                    "markets_limit": settings.mm_markets_limit,
                    "runtime_seconds": settings.mm_ws_runtime_seconds,
                    "max_messages": settings.mm_ws_max_messages,
                },
            )
            try:
                ws_runner = WsMarketMakerRunner(mm=mm, states=mm_states)
                ws_summary, mm_ws_results = await ws_runner.run(
                    markets=filtered,
                    runtime_seconds=settings.mm_ws_runtime_seconds,
                    max_messages=settings.mm_ws_max_messages,
                )
                db.insert_event("INFO", "mm ws telemetry", {"summary": ws_summary, "results": mm_ws_results})
                logger.info("mm ws summary", extra=ws_summary)
            except Exception as exc:
                logger.warning("mm ws failed", extra={"err": str(exc)})
                db.insert_event("WARNING", "mm ws failed", {"err": str(exc)})
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
