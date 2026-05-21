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
st.title("poly-market-arb-bot")

settings = get_settings()
db = Database(settings.db_full_path)


def _df(rows: list) -> pd.DataFrame:
    return pd.DataFrame([dict(row) for row in rows]) if rows else pd.DataFrame()


opps = _df(db.recent_opportunities(limit=200))
events = _df(db.recent_events(limit=100))
trades = _df(db.recent_trades(limit=200))
positions = _df(db.open_positions(limit=200))
resolved_positions = _df(db.resolved_positions(limit=200))
balance = db.latest_balance()
open_exposure = db.open_exposure_usd()
realized_pnl = db.realized_pnl_total()
curve = _df(db.equity_curve(limit=2000))

col1, col2, col3, col4 = st.columns(4)
col1.metric("Paper balance", f"${balance:,.2f}" if balance is not None else "—")
col2.metric("Open exposure", f"${open_exposure:,.2f}")
col3.metric("Realized PnL", f"${realized_pnl:+,.2f}")
col4.metric("Trades", len(trades))

st.subheader("Recent opportunities")
if opps.empty:
    st.info("No opportunities recorded yet.")
else:
    st.dataframe(opps, use_container_width=True, hide_index=True)

st.subheader("Recent trades")
if trades.empty:
    st.info("No trades yet.")
else:
    st.dataframe(trades, use_container_width=True, hide_index=True)

st.subheader("Open positions")
if positions.empty:
    st.info("No open positions.")
else:
    st.dataframe(positions, use_container_width=True, hide_index=True)

st.subheader("Resolved positions")
if resolved_positions.empty:
    st.info("No resolved positions yet.")
else:
    st.dataframe(resolved_positions, use_container_width=True, hide_index=True)

st.subheader("Equity curve")
if curve.empty:
    st.info("No balance snapshots yet.")
else:
    if "captured_at" in curve.columns:
        curve["captured_at"] = pd.to_datetime(curve["captured_at"])
        st.line_chart(curve.set_index("captured_at")["balance_usd"])

st.subheader("Recent events")
if events.empty:
    st.info("No events yet.")
else:
    st.dataframe(events, use_container_width=True, hide_index=True)
