# poly-market-arb-bot

Paper-only MVP for detecting and simulating bundle arbitrage on short BTC/ETH Polymarket markets.

## What it does

The bot:

- loads active Polymarket markets from Gamma API
- filters BTC/ETH 5-minute binary markets
- fetches YES and NO orderbooks
- estimates executable average fill prices from asks
- detects bundle opportunities where buying YES + NO is profitable after slippage and gas buffer
- opens paper trades and paper positions
- settles expired paper positions and calculates realized PnL
- stores everything in SQLite
- shows state in a Streamlit dashboard

## Current scope

Implemented now:

- paper mode only
- opportunity detection
- paper execution
- paper balance tracking
- settlement on expiry
- SQLite storage
- basic Streamlit dashboard

Not implemented yet:

- live trading
- production-grade market title parsing hardening

## Project structure

```text
src/clients/      Polymarket API client
src/markets/      Market parsing and filtering
src/analysis/     Orderbook walk and arbitrage detection
src/execution/    Paper execution and settlement
src/storage/      SQLite schema and queries
src/config/       Environment-based settings
src/utils/        Logging and retry helpers
scripts/          Entrypoints
dashboard/        Streamlit dashboard
```

## Requirements

- Python 3.11+
- Polymarket private key in `.env`

## Setup

### Linux / Ubuntu server

```bash
git clone <your-repo-url>
cd poly-market-arb-bot
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
cp .env.example .env
```

See also: [`deploy/ubuntu-setup.md`](deploy/ubuntu-setup.md)

### Windows

```bash
python -m venv .venv
.venv\Scripts\activate
pip install --upgrade pip
pip install -e ".[dev]"
copy .env.example .env
```

## Configuration

Minimal `.env` example:

```ini
POLYMARKET_PK=0x...
POLYMARKET_FUNDER=
POLYMARKET_SIGNATURE_TYPE=0
POLYMARKET_HOST=https://clob.polymarket.com
POLYMARKET_CHAIN_ID=137

SYMBOLS=BTC,ETH
SCAN_INTERVAL_SECONDS=2
MARKETS_REFRESH_SECONDS=30
MIN_EDGE_BPS=30
MAX_POSITION_USD=100
MAX_OPEN_EXPOSURE_USD=500
SLIPPAGE_BPS=5
GAS_ESTIMATE_USD=0.01
PAPER_TRADING=true
PAPER_STARTING_BALANCE_USD=1000
DB_PATH=data/poly_market_arb.db
LOG_LEVEL=INFO
```

## Run the bot

```bash
python scripts/paper_run.py
```

## Run the dashboard

In another terminal:

```bash
streamlit run dashboard/app.py
```

## Alternative install with requirements.txt

```bash
pip install -r requirements.txt
```

## systemd deployment

Service templates are included in:

- `deploy/systemd/poly-market-arb-bot.service`
- `deploy/systemd/poly-market-arb-dashboard.service`

They assume the project is deployed into:

- `/opt/poly-market-arb-bot`

Adjust `User`, `Group`, and paths if needed.

## What the dashboard shows

- paper balance
- open exposure
- realized PnL
- detected opportunities
- recent trades
- open positions
- resolved positions
- equity curve
- recent events

## Notes

- This version is intended for paper validation first.
- Market parsing for BTC/ETH 5m markets is still regex-based and should be verified against real Gamma responses before relying on it in production.
- SQLite database files are ignored by git.
- Research summary: see [`RESEARCH_RESULTS.md`](RESEARCH_RESULTS.md).

## Next steps

- harden market parsing against real market titles
- test more selective Polymarket-only microstructure hypotheses
- add live mode with safeguards only after paper validation
