# ARCHITECTURE — V3

Date: 2026-09-30  
Status: Proposed. Confirmed after user review.

---

## Design Principles

1. Every layer is independently testable.
2. Exchange is source of truth for execution.
3. Risk Engine cannot be bypassed — not by strategy, not by AI.
4. AI is research-only, not in the BUY/SELL decision path.
5. Default: `TRADING_DISABLED = True`. Live requires explicit activation.
6. Signal price, order price, fill price are always separate.
7. Funding is a cost, not just a gate.
8. NO_TRADE is a valid and frequent output.
9. Failed experiments are preserved, not deleted.
10. OOS is sealed after viewing. Holdout is consumed once.

---

## Decision Flow

```
MARKET DATA (exchange/bybit)
    │
    ▼
DATA QUALITY (data/quality.py)
    timestamp ordering, gaps, dedup, timezone, warmup, HTF alignment
    │
    ▼
FEATURES (features/)
    indicators derived from CLOSED bars only
    event_time and available_at are separate fields
    no future information allowed
    │
    ▼
REGIME (regime/)
    TREND_UP | TREND_DOWN | RANGE | HIGH_VOL | LOW_VOL | UNKNOWN
    UNKNOWN → NO_TRADE (hard stop, not a soft gate)
    thresholds derived from data, not inherited
    │
    ▼
STRATEGY (strategies/)
    pattern: EVENT → ENTRY_CONDITION → INVALIDATION → EXIT
    no indicator accumulation without per-indicator edge evidence
    │
    ▼
EDGE FILTER (research/edge_filter.py)
    explicit check: "has this hypothesis passed TRAIN→VALID→OOS?"
    if not validated: NO_TRADE
    │
    ▼
RISK ENGINE (risk/)
    risk per trade       (% of live balance)
    position size        (fixed-fractional, clock-injectable CB)
    SL distance          (from strategy, not hardcoded)
    max simultaneous     (portfolio check)
    portfolio risk       (total open risk ≤ threshold)
    daily loss limit     (live CB — currently missing in v2, built new in V3)
    max drawdown         (live CB — currently missing in v2, built new in V3)
    loss streak          (injectable clock)
    volatility shutdown  (NEW)
    TRADING_DISABLED     (kill switch — default True)
    ─── cannot be bypassed ───
    │
    ▼
ORDER PLAN (execution/order_plan.py)
    symbol, side, qty, type, price, sl, tp
    client_order_id (idempotency key)
    │
    ▼
EXECUTION (execution/)
    PostOnly limit (preferred)
    explicit policy for fallback (documented, not silent)
    no market order without explicit config flag
    │
    ▼
FILL (execution/fill_tracker.py)
    order_id, client_order_id, state, partial_fills, avg_fill, fee
    reconcile with exchange state on every poll
    │
    ▼
POSITION MANAGEMENT (execution/position_manager.py)
    SL/TP via exchange (exchange is source of truth)
    max hold hours
    emergency close
    │
    ▼
EXIT (strategies/exit.py)
    exchange-driven SL/TP, manual close, max hold, emergency
    ALL exit types reconciled in journal
    │
    ▼
RECONCILIATION (execution/reconciliation.py)
    periodic full state sync with exchange
    detects ghost positions, missing closes, fee drift
    │
    ▼
JOURNAL (journal/)
    signal_price, order_price, fill_price, avg_fill
    qty, fee, funding, slippage
    gross_pnl, net_pnl, R, MAE, MFE
    hold_hours, exit_reason
    strategy_version, regime, feature_snapshot
    │
    ▼
MONITORING (monitoring/)
    Telegram alerts: open/close/error/CB/drawdown
    health check: exchange ping, balance, open positions
```

---

## Module Structure

```
src/trading_engine/
├── common/
│   ├── types.py          # Candle, Trade, Signal, OrderPlan, Fill, ExitReason
│   ├── errors.py         # Typed exceptions
│   ├── time_utils.py     # Timezone handling, bar alignment
│   └── id_gen.py         # client_order_id generation
│
├── config/
│   └── settings.py       # env-loaded typed config (only used constants)
│
├── exchange/
│   ├── base.py           # Exchange ABC (extended vs v2)
│   └── bybit/
│       ├── client.py     # pybit session
│       ├── market_data.py
│       ├── orders.py
│       ├── positions.py
│       └── funding.py    # NEW: funding rate history, current rate
│
├── data/
│   ├── market_data.py    # OHLCV + OI + funding download and cache
│   └── quality.py        # gap check, dedup, HTF alignment validation
│
├── features/
│   ├── indicators.py     # ATR, EMA, RSI, ADX, etc. — pure functions
│   └── ohlcv_features.py # volume ratio, BB width, etc.
│
├── regime/
│   └── classifier.py     # Regime detection — thresholds from research
│
├── strategies/
│   ├── base.py           # Strategy ABC
│   └── exit.py           # Exit logic
│
├── research/
│   ├── hypothesis.py     # Hypothesis registry entry
│   ├── edge_filter.py    # Gate: only validated hypotheses trade
│   └── registry.py       # YAML/JSON store of all experiments
│
├── backtest/
│   ├── engine.py         # Bar-by-bar replay (REFACTOR of v2)
│   ├── historical_exchange.py  # HistoricalExchange adapter
│   ├── simulated_cb.py   # SimulatedCB extracted to common module
│   └── report.py         # Metrics + validation gate
│
├── risk/
│   ├── sizing.py         # Fixed-fractional (REUSE from v2)
│   ├── circuit.py        # CB with injectable clock (REFACTOR)
│   ├── drawdown.py       # Live drawdown CB (NEW)
│   ├── kill_switch.py    # TRADING_DISABLED (NEW)
│   └── filters.py        # Correlation, pair-lock (must work in backtest)
│
├── execution/
│   ├── order_plan.py     # OrderPlan dataclass
│   ├── orders.py         # Place/cancel/amend — with idempotency
│   ├── fill_tracker.py   # Track partial fills, avg_fill
│   ├── position_manager.py
│   └── reconciliation.py # Full state sync with exchange
│
├── portfolio/
│   └── portfolio.py      # Cross-symbol exposure tracking
│
├── journal/
│   └── journal.py        # SQLite, extended schema (REFACTOR from v2)
│
└── monitoring/
    └── telegram.py       # Alerts (REUSE from v2)
```

---

## AI Policy

### Allowed
- Research: hypothesis generation, literature review
- Market context: news, sentiment analysis for research
- Anomaly explanation: post-trade analysis
- Reporting: summaries, dashboards

### Forbidden
- Autonomous BUY/SELL signal generation that bypasses edge filter
- Override risk engine limits
- Increase leverage or position size
- Override circuit breaker
- Modify production strategy parameters

AI hypotheses follow the same path as all hypotheses:  
`HYPOTHESIS → DATA → BACKTEST → OOS → WALK-FORWARD → VALIDATION → (optional: PAPER → DEMO → LIVE)`

---

## Time Source Policy

`CircuitBreaker` and all time-dependent components receive an abstract clock:

```python
class TimeSource(Protocol):
    def now(self) -> datetime: ...
```

- Live: `WallClockTimeSource` → `datetime.now(timezone.utc)`
- Backtest: `SimulatedTimeSource(bar_ts)` → bar timestamp

This is the core lesson from the wall-clock CB bug found in v2.

---

## Price Separation Policy

Every trade record has four separate price fields:

| Field | When | Source |
|-------|------|--------|
| signal_price | When strategy generates signal | Last closed bar close |
| order_price | When order is submitted | Limit price or market |
| fill_price | When order fills (first partial) | Exchange fill report |
| average_fill_price | After all partials complete | Weighted average |

Journal stores all four. Sizing, SL, TP are calculated from `average_fill_price`, not `signal_price`.

---

## Default Safety State

```python
TRADING_DISABLED = True   # must be explicitly set to False to trade
LIVE_MODE = False         # paper/demo by default
```

Any code path that creates a real order must pass through `kill_switch.py`.  
Tests use `TRADING_DISABLED = True` always.
