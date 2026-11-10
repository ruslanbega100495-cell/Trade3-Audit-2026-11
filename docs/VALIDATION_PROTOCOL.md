# VALIDATION PROTOCOL — V3

Date: 2026-09-30

---

## Edge Evaluation (independent from production gate)

**The gate does NOT define edge. Edge is evaluated independently first.**

Edge must be demonstrated through ALL of:

| Dimension | What to measure |
|-----------|-----------------|
| Expectancy | EV = P(win)×AvgWin − P(loss)×AvgLoss − AvgFee − AvgFunding − AvgSlippage |
| Net PnL | After fees, funding, slippage — NOT gross |
| Profit Factor | Gross profit / Gross loss |
| Sharpe / Sortino | Risk-adjusted returns (Sortino for downside risk) |
| Max Drawdown | Peak-to-trough on equity curve |
| Trade count | Statistical significance (≥ 200 trades minimum in train) |
| Confidence intervals | 95% CI on expectancy — must be positive |
| OOS | Frozen parameters on held-out period |
| Walk-forward | Rolling windows — edge must be consistent |
| Parameter stability | ± 10-20% of selected params → metrics don't collapse |
| Regime stability | Edge present in TREND, RANGE, HIGH_VOL periods |
| Symbol stability | Edge present across 10+ symbols |
| Cost/slippage sensitivity | 2× fees+slippage → still positive expectancy |
| Robustness | Reasonable market perturbations don't flip sign |

Do NOT fit strategy parameters to pass any threshold. Thresholds are a production filter, not a design goal.

---

## Production Acceptance Gate (applied AFTER edge is proven)

These thresholds are a filter for controlled live deployment.  
Used ONLY at Steps 10-11 (Final Review → Controlled Live).

| Metric | Minimum |
|--------|---------|
| Win Rate | ≥ 45% |
| Profit Factor | ≥ 1.3 |
| Sharpe Ratio | ≥ 1.0 |
| Max Drawdown | < 15% |
| Recovery Factor | > 2.0 |
| Expectancy | > 0 (after all costs) |
| Trades per month | ≥ 20 (statistical significance) |
| Max hold time | < 24h |

All metrics measured AFTER: maker/taker fees, slippage, funding, spread.  
Not before. Not on gross PnL.

A strategy that passes edge evaluation but fails this gate is NOT deployed live.  
A strategy that passes this gate WITHOUT independent edge evaluation is NOT deployed live.

---

## Data Split Protocol

### Fixed splits (never tune on OOS or holdout)

```
2022-01-01 ─────────────────────────────────────────── 2026-09-30
     │                  │              │                    │
   TRAIN            VALIDATION       OOS               HOLDOUT
2022-01-01         2024-07-01     2025-04-01          2026-01-01
2024-06-30         2025-03-31     2025-12-31          2026-09-30
                                                      ─ SEALED ─
```

Exact dates are suggestions. Final splits set when research infrastructure is ready.  
Rule: TRAIN must contain multiple bull/bear/sideways regimes.  
Rule: HOLDOUT must contain at least 1 full regime cycle.

### Walk-forward

After OOS passes, run expanding or rolling walk-forward:
- Window: 6-month train, 1-month test
- All windows must be positive
- No window worse than -10% drawdown

---

## Validation Pipeline

```
Step 1: HYPOTHESIS
  - Registered in registry (HYP-NNN.yaml)
  - Clearly stated: what, why, which data, which features, parameter ranges
  - NO code yet

Step 2: TRAIN
  - Code written and tested
  - All parameter combinations run on TRAIN data
  - Best combination selected by Sharpe (or stated metric)
  - Parameters frozen after this step

Step 3: PARAMETER FREEZE
  - Selected parameters committed to git with hash
  - No further changes without creating new hypothesis version

Step 4: VALIDATION
  - Run on validation set with frozen parameters
  - Must pass gate criteria
  - If fails → back to hypothesis design, NOT parameter tuning

Step 5: OOS
  - Run with frozen parameters
  - OOS split is opened once
  - Must pass gate criteria
  - Any failure → new hypothesis version required

Step 6: WALK-FORWARD
  - Rolling windows on the full dataset (excluding holdout)
  - Must be net positive on all windows (or documented exception)

Step 7: FINAL HOLDOUT
  - Opened exactly once
  - Never used for any kind of selection or tuning
  - If fails → strategy is abandoned, not tuned
  - If passes → strategy is approved for paper trading

Step 8: PAPER
  - Same code as backtest (different execution adapter)
  - Compare: entries, exits, fills, slippage, fees, funding, PnL
  - Run for minimum 30 days with ≥ 20 trades

Step 9: BYBIT DEMO
  - Real exchange, no capital
  - Compare: backtest vs paper vs demo on all execution metrics
  - Investigate all material differences
  - Run for minimum 30 days

Step 10: FINAL REVIEW
  - Edge survives OOS, walk-forward, paper, demo
  - No unresolved P0/P1 issues
  - Risk engine tested (CB, drawdown, kill-switch all fire correctly)
  - Reconciliation tested
  - Emergency stop tested
  - Journal complete for all trade types

Step 11: CONTROLLED LIVE
  - Separate approval gate (requires explicit user confirmation)
  - Start with minimal exposure
  - No automatic position-size increase
```

---

## Version Control for Strategies

Every strategy has a version:

```
STRATEGY-{HYP_ID}-v{N}
```

Version increments when:
- Any parameter changes after TRAIN
- Any feature changes
- Any entry/exit logic changes
- Any regime filter changes

New version → full validation cycle restarts from Step 2.

After holdout is opened → even cosmetic changes require new version + new holdout.

---

## Backtest Correctness Requirements

Before any results are trusted, verify backtest engine:

| Test | Required |
|------|----------|
| 100 deterministic trade cases | YES |
| Signal price ≠ fill price on entry | YES |
| Limit order fill behavior | YES |
| Partial fills | YES |
| Maker fee on entry | YES |
| Taker fee on exit | YES |
| Funding cost included | YES |
| Slippage on both entry AND exit | YES |
| Intrabar SL+TP both touched → SL first | YES |
| Missing candles handled without lookahead | YES |
| Duplicate candles deduplicated | YES |
| HTF bar available only after close | YES |
| Balance evolution (compound, not fixed) | YES |
| Portfolio exposure check | YES |
| Reconciliation after every close | YES |

---

## Negative Results Policy

A negative result is a valid result. It stays in the registry.

When OOS fails:
- Record result in HYP-NNN.yaml
- Commit to git
- Do NOT delete
- Do NOT "adjust" parameters to pass OOS
- Analyze WHY it failed — this is research value

When walk-forward fails on some windows:
- Report all windows
- If most windows fail → strategy fails
- If 1-2 windows fail (documented regime-specific reasons) → document, continue to holdout with caution

---

## Multiple Testing Adjustment

If more than 10 parameter combinations are tested on TRAIN:

Apply Deflated Sharpe Ratio (DSR) to adjust for overfitting.  
The reported Sharpe is the DSR, not the raw backtest Sharpe.

Reference: `Lopez de Prado — Advances in Financial Machine Learning, Chapter 8`.

---

## Funding in Backtest

Funding must be modeled as a cost:

```
Funding cost per 8h period = position_size × mark_price × funding_rate
```

For each position held through a funding timestamp (00:00, 08:00, 16:00 UTC):
- LONG position: pays positive funding rate
- SHORT position: receives positive funding rate (negative cost)
- Net effect subtracted from PnL

Default assumption if no funding history available: use 0.01% per 8h (conservative positive rate).  
Best practice: use actual historical funding rate from Bybit API.
