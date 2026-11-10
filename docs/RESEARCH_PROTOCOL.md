# RESEARCH PROTOCOL — V3

Date: 2026-09-30

---

## Core Rule

Before any strategy trades live, it must prove edge through this full chain:

```
DATA → HYPOTHESIS → TRAIN → FREEZE → VALIDATION → OOS → WALK-FORWARD → FINAL HOLDOUT → PAPER → DEMO → LIVE
```

No skipping. Each step is gated by measurable criteria.

---

## Hypothesis Registry

Every hypothesis receives an ID before any code is written.

### Entry format

```yaml
id: HYP-001
name: Trend Breakout — H1 N-bar high
date: YYYY-MM-DD
researcher: <name>
status: OPEN | BACKTEST | VALIDATION | OOS | FAILED | PASSED_OOS

hypothesis: >
  Price breaks above N-bar rolling high on above-average volume →
  continuation expected over M bars.

market: Bybit USDT perpetuals
symbols: [BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT]
timeframe: H1
data_required: [OHLCV, volume]
features: [N_bar_high, volume_ratio]

parameter_ranges:
  N: [10, 20, 40]
  volume_threshold: [1.2, 1.5, 2.0]

costs:
  maker_fee: 0.02%
  taker_fee: 0.075%
  slippage_entry: 0.1%
  slippage_exit: 0.1%
  funding: modeled

split:
  train: 2022-01-01 / 2024-06-30
  validation: 2024-07-01 / 2025-03-31
  oos: 2025-04-01 / 2025-12-31
  holdout: 2026-01-01 / 2026-09-30  # SEALED — do not use until all prior steps pass

results:
  train: null
  validation: null
  oos: null
  walk_forward: null
  holdout: null

decision: null
rejection_reason: null
```

### Registry location

`research/registry/HYP-NNN.yaml`

Failed hypotheses stay in the registry. Never delete them.

---

## Hypotheses To Research (A–J)

Status: NOT STARTED for all.

| ID | Name | Key data needed | Prior evidence |
|----|------|-----------------|----------------|
| HYP-A | Trend Breakout | OHLCV | None tested in V3 |
| HYP-B | Breakout + Retest | OHLCV | None tested in V3 |
| HYP-C | Trend Pullback Continuation | OHLCV, EMA, ADX | v2 used similar logic — failed OOS. Test independently on clean data. |
| HYP-D | Volatility Expansion (Squeeze→Expansion) | OHLCV, ATR, BBW | v1 marked SQUEEZE as disabled. Research why. |
| HYP-E | Momentum + Volume | OHLCV, volume | v2 had volume gate — failed OOS. Volume alone may not be sufficient. |
| HYP-F | Price + Open Interest | OHLCV, OI | No data collected yet. Collect first. |
| HYP-G | Funding + OI | funding history, OI | No data collected yet. Collect first. |
| HYP-H | Basis (perp vs spot) | perp OHLCV, spot OHLCV | No data collected yet. Collect first. |
| HYP-I | Order Flow / Liquidity | order book depth | Likely unavailable historically with sufficient quality. Skip until proven available. |
| HYP-J | Mean Reversion | OHLCV | Must prove stationarity before testing trading logic. |

---

## Prohibited Research Patterns

### 1. Circular regime definition
Do NOT define regime as `ADX < 20 = RANGE` and then test mean reversion in RANGE.  
That makes the mean-reversion proof depend on ADX, not on price stationarity.  
Prove mean-reversion properties first (stationarity, autocorrelation, half-life), then filter by regime separately.

### 2. Score / probability fabrication
Do NOT generate probability by summing indicator scores.  
`50 + 10 + 15 = 85%` is NOT probability. It has no statistical meaning.  
If probability is needed, estimate it from historical outcomes:  
`P(TP before SL | features)` → calibrated on TRAIN → validated on OOS.

### 3. Indicator accumulation
Do NOT add a new indicator because it seems related.  
Each additional feature must demonstrate incremental edge on holdout-unseen data.  
More features → more parameters → more overfitting.

### 4. Tuning after OOS
After OOS is run, the strategy version is frozen.  
Any parameter change creates a new version with a new OOS split.  
Once the holdout is opened, it is consumed.

### 5. Selection bias
Do NOT run 50 parameter combinations and report the best.  
Report all combinations. Use Deflated Sharpe Ratio to account for multiple testing.

### 6. Recency bias
Do NOT validate on only the last 3 months because the market "changed."  
Walk-forward must cover multiple market regimes including periods similar to PLAN-STRATEGY-v2.md's failing half (2025 H1).

---

## Data Requirements

### Available in donor
- Bybit H1/H4 OHLCV: 2024-07-23 to 2026-08-12 for BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT
- Current funding rate (v1, not history)

### Must collect for V3 research
- Bybit USDT perp OHLCV: extend to full 3+ years for walk-forward (API: get_kline)
- Funding rate history: Bybit `/v5/market/funding/history` (up to 200 per request)
- Open Interest history: Bybit `/v5/market/open-interest`
- More symbols: at least 10-15 for symbol-stability testing
- Spot prices for basis calculation (BTC, ETH spot)

### Data quality requirements
Every dataset must pass quality.py checks before research:
- Timestamp monotonic ascending
- No duplicates (same timestamp)
- No gaps > N bars (configurable per research)
- All bars are closed (not in progress)
- HTF bars aligned to actual close time
- No future information in any feature

---

## Expectancy Formula

For every tested hypothesis:

```
EV = P(win) × AvgWin − P(loss) × AvgLoss − AvgFee − AvgFunding − AvgSlippage
```

All values measured from data. Never estimated.  
Measured on TRAIN. Verified on VALIDATION. Tested on OOS.

---

## Overfitting Controls

| Check | When |
|-------|------|
| Parameter sensitivity (± 10-20% of selected value) | After TRAIN |
| Symbol stability (edge holds across 10+ symbols) | After TRAIN |
| Regime stability (edge holds in TREND and RANGE) | After TRAIN |
| Temporal stability (walk-forward windows all positive) | Walk-forward |
| Cost sensitivity (double fees/slippage) | After TRAIN |
| Funding sensitivity (funding 3× normal) | After TRAIN |
| Trade concentration (no >20% PnL from single trade) | After TRAIN |
| Multiple testing correction (Deflated Sharpe Ratio) | After TRAIN if >10 combos tested |
| Purged CV / embargo | Optional, for features with autocorrelation |
| CPCV / PBO | If claiming high Sharpe |

---

## Research Infrastructure (Phase 6, not yet built)

Files to create:
```
research/
  registry/           # HYP-NNN.yaml files
  hypotheses/         # per-hypothesis notebooks/scripts
  datasets/           # cached CSV data
  results/            # outputs, charts, walk-forward reports
```

Tools to build:
- `scripts/collect_data.py` — download and cache OHLCV, funding, OI
- `scripts/run_hypothesis.py` — run a hypothesis end-to-end
- `scripts/walk_forward.py` — walk-forward validation harness
- `research/registry.py` — read/write hypothesis registry
