from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.config.settings import get_settings
from src.storage.db import Database

st.set_page_config(page_title="poly-market-arb-bot", layout="wide")

settings = get_settings()
db = Database(settings.db_full_path)


def _df(rows: list) -> pd.DataFrame:
    return pd.DataFrame([dict(row) for row in rows]) if rows else pd.DataFrame()


def _event_df(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows) if rows else pd.DataFrame()


opps = _df(db.recent_opportunities(limit=200))
events = _df(db.recent_events(limit=100))
trades = _df(db.recent_trades(limit=200))
positions = _df(db.open_positions(limit=200))
resolved_positions = _df(db.resolved_positions(limit=200))
curve = _df(db.equity_curve(limit=2000))
scan_events = _event_df(db.recent_scan_events(limit=100))
near_arbs = _event_df(db.recent_near_arb_markets(limit=200))
preorder_events = _event_df(db.recent_preorder_events(limit=100))
preorder_results = _event_df(db.recent_preorder_results(limit=200))
preorder_candidates = _event_df(db.recent_preorder_candidates(limit=200))

balance = db.latest_balance()
open_exposure = db.open_exposure_usd()
realized_pnl = db.realized_pnl_total()

st.title("Polymarket short up/down scanner")
st.caption("Paper-mode dashboard for discovery, near-arb tracking, and execution telemetry.")

latest_scan = scan_events.iloc[0] if not scan_events.empty else None
latest_preorder = preorder_events.iloc[0] if not preorder_events.empty else None

top1, top2, top3, top4, top5 = st.columns(5)
top1.metric("Paper balance", f"${balance:,.2f}" if balance is not None else "—")
top2.metric("Open exposure", f"${open_exposure:,.2f}")
top3.metric("Realized PnL", f"${realized_pnl:+,.2f}")
top4.metric("Trades", len(trades))
top5.metric("Open positions", len(positions))

st.subheader("Scan health")
scan1, scan2, scan3, scan4, scan5 = st.columns(5)
scan1.metric("Markets discovered", int(latest_scan["discovered"]) if latest_scan is not None and "discovered" in latest_scan else 0)
scan2.metric("Markets processed", int(latest_scan["processed"]) if latest_scan is not None and "processed" in latest_scan else 0)
scan3.metric("Opportunities", int(latest_scan["opportunities"]) if latest_scan is not None and "opportunities" in latest_scan else 0)
scan4.metric("Executed", int(latest_scan["executed"]) if latest_scan is not None and "executed" in latest_scan else 0)
scan5.metric("Errors", int(latest_scan["errors"]) if latest_scan is not None and "errors" in latest_scan else 0)

if latest_preorder is not None and "summary" in latest_preorder:
    summary = latest_preorder["summary"] if isinstance(latest_preorder["summary"], dict) else {}
    rolling = latest_preorder["rolling_summary"] if isinstance(latest_preorder.get("rolling_summary"), dict) else {}
    st.subheader("Pre-order paper simulation")
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Full fills", int(summary.get("full_fill", 0)))
    p2.metric("Over-budget fills", int(summary.get("full_fill_over_budget", 0)))
    p3.metric("Partial fills", int(summary.get("partial_fill", 0)))
    p4.metric("No fills", int(summary.get("no_fill", 0)))
    p5, p6, p7, p8 = st.columns(4)
    p5.metric("Full fill rate", f"{float(summary.get('full_fill_rate', 0.0)) * 100:.1f}%")
    p6.metric("Rolling full fill rate", f"{float(rolling.get('full_fill_rate', 0.0)) * 100:.1f}%")
    p7.metric("Avg partial exit loss", f"${float(summary['avg_partial_exit_loss']):.3f}" if summary.get("avg_partial_exit_loss") is not None else "—")
    p8.metric("Rolling partial exit loss", f"${float(rolling['avg_partial_exit_loss']):.3f}" if rolling.get("avg_partial_exit_loss") is not None else "—")

left, right = st.columns((1.2, 1.8))

with left:
    st.subheader("Best near-arbs")
    if near_arbs.empty:
        st.info("No scan telemetry yet.")
    else:
        display = near_arbs.copy()
        preferred = [
            "created_at",
            "slug",
            "symbol",
            "timeframe_minutes",
            "ask_up",
            "ask_down",
            "sum_asks",
            "up_asks",
            "down_asks",
        ]
        cols = [col for col in preferred if col in display.columns]
        display = display[cols]
        st.dataframe(display, use_container_width=True, hide_index=True)

with right:
    st.subheader("Recent scan summaries")
    if scan_events.empty:
        st.info("No scan summaries yet.")
    else:
        display = scan_events.copy()
        preferred = ["created_at", "discovered", "processed", "opportunities", "executed", "errors"]
        cols = [col for col in preferred if col in display.columns]
        st.dataframe(display[cols], use_container_width=True, hide_index=True)

st.subheader("Pre-order results")
if preorder_results.empty:
    st.info("Pre-order simulation is not enabled or no telemetry yet.")
else:
    display = preorder_results.copy()
    preferred = [
        "created_at",
        "slug",
        "symbol",
        "timeframe_minutes",
        "target_price_up",
        "target_price_down",
        "filled_up",
        "filled_down",
        "best_ask_up",
        "best_ask_down",
        "distance_up",
        "distance_down",
        "missing_leg",
        "bundle_cost",
        "expected_pnl",
        "partial_exit_loss",
        "status",
    ]
    cols = [col for col in preferred if col in display.columns]
    st.dataframe(display[cols], use_container_width=True, hide_index=True)

st.subheader("Best pre-order candidates")
if preorder_candidates.empty:
    st.info("No pre-order candidate telemetry yet.")
else:
    display = preorder_candidates.copy()
    preferred = [
        "created_at",
        "slug",
        "symbol",
        "timeframe_minutes",
        "status",
        "best_ask_up",
        "best_ask_down",
        "distance_up",
        "distance_down",
        "missing_leg",
        "partial_exit_loss",
    ]
    cols = [col for col in preferred if col in display.columns]
    st.dataframe(display[cols], use_container_width=True, hide_index=True)

st.subheader("Equity curve")
if curve.empty:
    st.info("No balance snapshots yet.")
else:
    if "captured_at" in curve.columns:
        curve["captured_at"] = pd.to_datetime(curve["captured_at"])
        st.line_chart(curve.set_index("captured_at")[["balance_usd"]])

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["Recent opportunities", "Trades", "Open positions", "Resolved positions", "Events"]
)

with tab1:
    if opps.empty:
        st.info("No opportunities recorded yet.")
    else:
        st.dataframe(opps, use_container_width=True, hide_index=True)

with tab2:
    if trades.empty:
        st.info("No trades yet.")
    else:
        st.dataframe(trades, use_container_width=True, hide_index=True)

with tab3:
    if positions.empty:
        st.info("No open positions.")
    else:
        st.dataframe(positions, use_container_width=True, hide_index=True)

with tab4:
    if resolved_positions.empty:
        st.info("No resolved positions yet.")
    else:
        st.dataframe(resolved_positions, use_container_width=True, hide_index=True)

with tab5:
    if events.empty:
        st.info("No events yet.")
    else:
        st.dataframe(events, use_container_width=True, hide_index=True)
