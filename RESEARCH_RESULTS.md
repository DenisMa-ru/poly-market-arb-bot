## Research results — Polymarket-only paper experiments

Scope: short BTC/ETH up/down markets on Polymarket, paper mode only.

### Tested hypotheses

1. Pre-order bundle simulation
2. Passive market making v1
3. WebSocket market making v2/v3
4. WebSocket momentum/imbalance signal v1/v2

### Main findings

#### 1) Pre-order bundle simulation
- Full fills were not observed reliably.
- Partial fills were common.
- Typical result was negative after forced partial exit.
- Conclusion: not a viable paper strategy in tested short markets.

#### 2) Passive market making
- REST-like paper MM with wider and tighter spreads mostly produced zero fills.
- WS-based MM confirmed that quotes were often near the touch, but stable two-sided fill flow was not observed.
- Even with aggressive settings, fills were infrequent and economics were not convincingly positive.
- Conclusion: simple symmetric maker logic is not supported by the observed data.

#### 3) WS market making telemetry work
- WS diagnostics were validated against Polymarket market subscriptions.
- Paper MM WS telemetry now records message counts, book events, price changes, inventory, execution counters, and quote-distance metrics.
- This infrastructure is useful even though the tested MM alpha was weak.

#### 4) WS signal paper strategy
- A simple streak-based momentum entry generated trades, but results were consistently negative.
- Observed pattern: buying at ask and immediately marking against bid produced repeated one-tick losses.
- Tighter entry filters and reversal exits did not make the hypothesis profitable.
- Conclusion: naive taker-style momentum on these markets does not overcome the spread.

### Practical conclusion

At this stage, the repository has a usable paper research framework for Polymarket:
- market discovery
- paper execution tracking
- WS diagnostics
- WS MM telemetry
- WS signal telemetry
- dashboard visibility

But none of the tested simple alpha ideas have been validated as robustly profitable:
- pre-order bundles: weak
- passive maker MM: weak
- simple WS momentum signal: weak

### Recommended next direction

If continuing Polymarket-only research, the next hypothesis should be more selective and microstructure-aware, for example:
- regime-based event selection
- imbalance only when expected move is larger than one tick
- resolution-proximity behavior
- signal logic that explicitly models spread cost before entry

This file is intended as a checkpoint so future iterations do not repeat the same low-level experiments blindly.
