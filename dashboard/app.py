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


def _show_table(df: pd.DataFrame, preferred: list[str], *, empty_text: str) -> None:
    if df.empty:
        st.info(empty_text)
        return
    cols = [col for col in preferred if col in df.columns]
    st.dataframe(df[cols] if cols else df, use_container_width=True, hide_index=True)


def _pair_mm_status(summary: dict[str, object]) -> tuple[str, str]:
    open_skew = int(summary.get("opened_new_skew_count", 0))
    replenishes = int(summary.get("replenish_count", 0))
    blocked = int(summary.get("blocked_min_new_skew_edge", 0))
    avg_replenish = summary.get("avg_replenish_cost_per_pair")
    net_pnl = float(summary.get("net_pnl", 0.0))

    if replenishes > 0 and avg_replenish is not None and float(avg_replenish) > 0.99:
        return "warning", "Replenish still looks expensive. Inventory is being rebuilt near or above par."
    if open_skew == 0 and blocked > 0:
        return "info", "Bot is mostly filtering weak fresh skew. Low activity may be intentional."
    if net_pnl < -0.05:
        return "warning", "Recent pair-MM net PnL is negative. Inventory cycle may still be too costly."
    if open_skew > 0 and replenishes == 0:
        return "success", "Skew is opening without immediate aggressive re-arm."
    return "info", "Watch opens, unwinds, replenish cost, and blocked skew to judge expectancy."


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
mm_events = _event_df(db.recent_mm_events(limit=100))
mm_results = _event_df(db.recent_mm_results(limit=200))
mm_ws_events = _event_df(db.recent_mm_ws_events(limit=100))
mm_ws_results = _event_df(db.recent_mm_ws_results(limit=200))
ws_signal_events = _event_df(db.recent_ws_signal_events(limit=100))
ws_signal_results = _event_df(db.recent_ws_signal_results(limit=200))
pair_mm_events = _event_df(db.recent_pair_mm_events(limit=100))
pair_mm_results = _event_df(db.recent_pair_mm_results(limit=200))
reward_market_events = _event_df(db.recent_reward_market_events(limit=100))
reward_market_results = _event_df(db.recent_reward_market_results(limit=200))

balance = db.latest_balance()
open_exposure = db.open_exposure_usd()
realized_pnl = db.realized_pnl_total()

st.title("Polymarket short up/down scanner")
st.caption("Paper-mode dashboard for discovery, near-arb tracking, and execution telemetry.")

latest_scan = scan_events.iloc[0] if not scan_events.empty else None
latest_preorder = preorder_events.iloc[0] if not preorder_events.empty else None
latest_mm = mm_events.iloc[0] if not mm_events.empty else None
latest_mm_ws = mm_ws_events.iloc[0] if not mm_ws_events.empty else None
latest_ws_signal = ws_signal_events.iloc[0] if not ws_signal_events.empty else None
latest_pair_mm = pair_mm_events.iloc[0] if not pair_mm_events.empty else None
latest_reward_market = reward_market_events.iloc[0] if not reward_market_events.empty else None

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

if any(
    row is not None and "summary" in row
    for row in [latest_preorder, latest_mm, latest_mm_ws, latest_ws_signal]
):
    with st.expander("Other strategy snapshots", expanded=False):
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

        if latest_mm is not None and "summary" in latest_mm:
            summary = latest_mm["summary"] if isinstance(latest_mm["summary"], dict) else {}
            st.subheader("Paper market making")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Quoted markets", int(summary.get("markets", 0)))
            m2.metric("Fills", int(summary.get("fills", 0)))
            m3.metric("Fill rate", f"{float(summary.get('fill_rate', 0.0)) * 100:.1f}%")
            m4.metric("Replaces", int(summary.get("replaces", 0)))
            m5, m6, m7, m8 = st.columns(4)
            m5.metric("Bid fills", int(summary.get("bid_fills", 0)))
            m6.metric("Ask fills", int(summary.get("ask_fills", 0)))
            m7.metric("Realized spread", f"${float(summary.get('realized_spread_capture', 0.0)):.3f}")
            m8.metric("Unrealized PnL", f"${float(summary.get('unrealized_pnl', 0.0)):.3f}")

        if latest_mm_ws is not None and "summary" in latest_mm_ws:
            summary = latest_mm_ws["summary"] if isinstance(latest_mm_ws["summary"], dict) else {}
            st.subheader("Paper market making WS v2")
            w1, w2, w3, w4 = st.columns(4)
            w1.metric("WS messages", int(summary.get("messages", 0)))
            w2.metric("Book events", int(summary.get("books", 0)))
            w3.metric("Price changes", int(summary.get("price_changes", 0)))
            w4.metric("Quoted markets", int(summary.get("quoted_markets", 0)))
            w5, w6, w7, w8 = st.columns(4)
            w5.metric("Fills", int(summary.get("fills", 0)))
            w6.metric("Bid fills", int(summary.get("bid_fills", 0)))
            w7.metric("Ask fills", int(summary.get("ask_fills", 0)))
            w8.metric("Net inventory", f"{float(summary.get('net_inventory', 0.0)):.2f}")

        if latest_ws_signal is not None and "summary" in latest_ws_signal:
            summary = latest_ws_signal["summary"] if isinstance(latest_ws_signal["summary"], dict) else {}
            st.subheader("WS signal paper strategy")
            s1, s2, s3, s4 = st.columns(4)
            s1.metric("Trades", int(summary.get("trades", 0)))
            s2.metric("Wins", int(summary.get("wins", 0)))
            s3.metric("Losses", int(summary.get("losses", 0)))
            s4.metric("Win rate", f"{float(summary.get('win_rate', 0.0)) * 100:.1f}%")
            s5, s6, s7 = st.columns(3)
            s5.metric("WS messages", int(summary.get("messages", 0)))
            s6.metric("Avg PnL", f"${float(summary.get('avg_pnl', 0.0)):.3f}")
            s7.metric("Total PnL", f"${float(summary.get('total_pnl', 0.0)):.3f}")

if latest_reward_market is not None and "summary" in latest_reward_market:
    summary = latest_reward_market["summary"] if isinstance(latest_reward_market["summary"], dict) else {}
    st.subheader("Reward-first market making")
    r1, r2, r3, r4, r5 = st.columns(5)
    r1.metric("Selected markets", int(summary.get("markets", 0)))
    r2.metric("Reward-eligible", int(summary.get("reward_eligible_markets", 0)))
    r3.metric("Fills", int(summary.get("fills", 0)))
    r4.metric("Avg fill rate", f"{float(summary.get('avg_fill_rate', 0.0)) * 100:.1f}%")
    r5.metric("Avg spread", f"{float(summary.get('avg_spread_bps', 0.0)):.1f} bps")
    r6, r7, r8, r9 = st.columns(4)
    r6.metric("Reward PnL", f"${float(summary.get('reward_pnl', 0.0)):.4f}")
    r7.metric("Realized PnL", f"${float(summary.get('realized_pnl', 0.0)):.4f}")
    r8.metric("Net inventory", f"{float(summary.get('net_inventory', 0.0)):.2f}")
    r9.metric("Net PnL", f"${float(summary.get('net_pnl', 0.0)):.4f}")

st.subheader("Reward market focus")
reward_left, reward_right = st.columns((1.2, 1.8))

with reward_left:
    if latest_reward_market is None or "summary" not in latest_reward_market:
        st.info("No reward market summary yet.")
    else:
        summary = latest_reward_market["summary"] if isinstance(latest_reward_market["summary"], dict) else {}
        selected = summary.get("selected_markets") if isinstance(summary.get("selected_markets"), list) else []
        st.dataframe(pd.DataFrame(selected), use_container_width=True, hide_index=True)

with reward_right:
    _show_table(
        reward_market_results.head(20),
        [
            "created_at",
            "slug",
            "question",
            "status",
            "reward_rate_per_day",
            "quoted_spread_bps",
            "reward_eligible",
            "filled_bid",
            "filled_ask",
            "fill_rate",
            "net_inventory",
            "reward_pnl_delta",
            "realized_pnl_delta",
            "net_pnl",
        ],
        empty_text="No reward market telemetry yet.",
    )

if latest_pair_mm is not None and "summary" in latest_pair_mm:
    summary = latest_pair_mm["summary"] if isinstance(latest_pair_mm["summary"], dict) else {}
    status_level, status_text = _pair_mm_status(summary)
    if status_level == "success":
        st.success(status_text)
    elif status_level == "warning":
        st.warning(status_text)
    else:
        st.info(status_text)
    st.subheader("Pair market making paper strategy")
    p1, p2, p3, p4, p5 = st.columns(5)
    p1.metric("Markets", int(summary.get("markets", 0)))
    p2.metric("Opened skew", int(summary.get("opened_new_skew_count", 0)))
    p3.metric("Unwinds", int(summary.get("unwind_count", 0)))
    p4.metric("Repairs", f"{float(summary.get('repaired_pairs', 0.0)):.1f}")
    p5.metric("Blocked new skew", int(summary.get("blocked_min_new_skew_edge", 0)))
    p6, p7, p8, p9 = st.columns(4)
    p6.metric("Replenish count", int(summary.get("replenish_count", 0)))
    p7.metric("Avg replenish cost", f"{float(summary.get('avg_replenish_cost_per_pair', 0.0)):.3f}" if summary.get("avg_replenish_cost_per_pair") is not None else "—")
    p8.metric("Reward PnL", f"${float(summary.get('reward_pnl', 0.0)):.4f}")
    p9.metric("Net PnL", f"${float(summary.get('net_pnl', 0.0)):.4f}")

st.subheader("Pair-MM evaluation focus")
focus_left, focus_right = st.columns((1.2, 1.8))

with focus_left:
    if latest_pair_mm is None or "summary" not in latest_pair_mm:
        st.info("No pair-MM summary yet.")
    else:
        summary = latest_pair_mm["summary"] if isinstance(latest_pair_mm["summary"], dict) else {}
        focus_rows = pd.DataFrame(
            [
                {"Metric": "Opened new skew", "Value": int(summary.get("opened_new_skew_count", 0))},
                {"Metric": "Unwinds", "Value": int(summary.get("unwind_count", 0))},
                {"Metric": "Repairs", "Value": float(summary.get("repaired_pairs", 0.0))},
                {"Metric": "Replenish count", "Value": int(summary.get("replenish_count", 0))},
                {"Metric": "Replenish notional cost", "Value": float(summary.get("replenish_notional_cost", 0.0))},
                {"Metric": "Avg replenish cost / pair", "Value": summary.get("avg_replenish_cost_per_pair")},
                {"Metric": "Open skew markets", "Value": int(summary.get("open_skew_markets", 0))},
            ]
        )
        st.dataframe(focus_rows, use_container_width=True, hide_index=True)

with focus_right:
    _show_table(
        pair_mm_results.head(20),
        [
            "created_at",
            "slug",
            "status",
            "opened_new_skew",
            "unwound_free_inventory",
            "repair_size",
            "split_pairs",
            "replenish_cost",
            "pair_ask_sum",
            "sold_up",
            "sold_down",
            "reward_pnl_delta",
            "realized_pnl_delta",
            "net_pnl_delta",
        ],
        empty_text="No pair-MM telemetry yet.",
    )

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
    _show_table(scan_events, ["created_at", "discovered", "processed", "opportunities", "executed", "errors"], empty_text="No scan summaries yet.")

with st.expander("Detailed strategy tables", expanded=False):
    tab_a, tab_b, tab_c, tab_d = st.tabs(["Pre-order", "MM", "WS signal", "Raw DB tables"])

    with tab_a:
        _show_table(preorder_results, ["created_at", "slug", "symbol", "timeframe_minutes", "bundle_cost", "expected_pnl", "partial_exit_loss", "status"], empty_text="Pre-order simulation is not enabled or no telemetry yet.")
        _show_table(preorder_candidates, ["created_at", "slug", "symbol", "timeframe_minutes", "status", "best_ask_up", "best_ask_down", "distance_up", "distance_down", "partial_exit_loss"], empty_text="No pre-order candidate telemetry yet.")

    with tab_b:
        _show_table(mm_results, ["created_at", "slug", "symbol", "timeframe_minutes", "bid", "ask", "filled_bid", "filled_ask", "inventory_before", "inventory_after", "spread_capture", "unrealized_pnl", "status"], empty_text="Market making telemetry is not enabled or no data yet.")
        _show_table(mm_ws_results, ["created_at", "slug", "symbol", "timeframe_minutes", "bid", "ask", "filled_bid", "filled_ask", "inventory_before", "inventory_after", "spread_capture", "unrealized_pnl", "status"], empty_text="Market making WS telemetry is not enabled or no data yet.")

    with tab_c:
        _show_table(ws_signal_results, ["created_at", "slug", "symbol", "timeframe_minutes", "entry_price", "exit_price", "pnl", "hold_seconds", "entry_reason", "exit_reason", "status"], empty_text="WS signal telemetry is not enabled or no data yet.")

    with tab_d:
        raw1, raw2, raw3, raw4, raw5 = st.tabs(["Recent opportunities", "Trades", "Open positions", "Resolved positions", "Events"])
        with raw1:
            _show_table(opps, list(opps.columns), empty_text="No opportunities recorded yet.")
        with raw2:
            _show_table(trades, list(trades.columns), empty_text="No trades yet.")
        with raw3:
            _show_table(positions, list(positions.columns), empty_text="No open positions.")
        with raw4:
            _show_table(resolved_positions, list(resolved_positions.columns), empty_text="No resolved positions yet.")
        with raw5:
            _show_table(events, list(events.columns), empty_text="No events yet.")

st.subheader("Equity curve")
if curve.empty:
    st.info("No balance snapshots yet.")
else:
    if "captured_at" in curve.columns:
        curve["captured_at"] = pd.to_datetime(curve["captured_at"])
        st.line_chart(curve.set_index("captured_at")[["balance_usd"]])
