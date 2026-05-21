PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS opportunities (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    detected_at     TEXT NOT NULL,
    market_id       TEXT NOT NULL,
    question        TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    expiry_at       TEXT,
    ask_yes         REAL NOT NULL,
    ask_no          REAL NOT NULL,
    avg_yes_price   REAL NOT NULL,
    avg_no_price    REAL NOT NULL,
    size_contracts  REAL NOT NULL,
    gross_edge_usd  REAL NOT NULL,
    slippage_usd    REAL NOT NULL,
    gas_usd         REAL NOT NULL,
    net_edge_usd    REAL NOT NULL,
    edge_bps        INTEGER NOT NULL,
    notional_usd    REAL NOT NULL,
    decision        TEXT NOT NULL,
    decision_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_opportunities_detected ON opportunities(detected_at DESC);

CREATE TABLE IF NOT EXISTS bot_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   TEXT NOT NULL,
    level        TEXT NOT NULL,
    message      TEXT NOT NULL,
    context_json TEXT
);

CREATE TABLE IF NOT EXISTS trades (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_id INTEGER NOT NULL REFERENCES opportunities(id),
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    mode          TEXT NOT NULL,
    status        TEXT NOT NULL,
    expected_pnl  REAL,
    realized_pnl  REAL,
    notes         TEXT
);

CREATE INDEX IF NOT EXISTS idx_trades_started ON trades(started_at DESC);

CREATE TABLE IF NOT EXISTS legs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id        INTEGER NOT NULL REFERENCES trades(id),
    token_id        TEXT NOT NULL,
    outcome         TEXT NOT NULL,
    requested_size  REAL NOT NULL,
    requested_price REAL NOT NULL,
    filled_size     REAL,
    avg_fill_price  REAL,
    fee_usd         REAL,
    status          TEXT NOT NULL,
    submitted_at    TEXT NOT NULL,
    settled_at      TEXT
);

CREATE INDEX IF NOT EXISTS idx_legs_trade ON legs(trade_id);

CREATE TABLE IF NOT EXISTS positions (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id             INTEGER NOT NULL REFERENCES trades(id),
    market_id            TEXT NOT NULL,
    question             TEXT NOT NULL,
    symbol               TEXT NOT NULL,
    expiry_at            TEXT,
    status               TEXT NOT NULL,
    size_contracts       REAL NOT NULL,
    invested_usd         REAL NOT NULL,
    expected_payout_usd  REAL NOT NULL,
    realized_pnl         REAL,
    resolved_at          TEXT
);

CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);

CREATE TABLE IF NOT EXISTS balance_snapshots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at   TEXT NOT NULL,
    balance_usd   REAL NOT NULL,
    note          TEXT
);

CREATE INDEX IF NOT EXISTS idx_balance_captured ON balance_snapshots(captured_at DESC);
