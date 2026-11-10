# V6 — HYP-A-001 Readiness Report
Date: 2026-10-25

## Summary

**NOT_READY**

HYP-A-001/TREND_UP/LONG passes all 6 PRIMARY criteria in the CANDIDATE_GATE (TRAIN data).
Advancement to VALIDATION is blocked by three concrete issues documented below.

---

## Evidence — 10 Criteria

### 1. Hypothesis Formulation

- **Signal**: candle close > max(previous 20-bar highs) = LONG breakout; close < min(previous 20-bar lows) = SHORT breakout.
- **Entry**: at `candle[i].available_at` (after bar i closes, using bars i-20..i-1 only).
- **Exit**: event study only — no exit rule. Forward return measured at close of bar at +H (H = 4, 8, 16, 32 bars).
- **Regime filter** (added in regime-conditional study): only TREND_UP bars qualify for LONG.
- Source: `src/trading_engine/research/hypotheses/hyp_a_001.py`, `docs/research/HYP-A-001_REAL_DATA_REPORT.md`

### 2. What WF=0.75 Means

**Two different walk-forward metrics exist — they must not be confused:**

**WF-A (original, unconditional, Phase 7.2):**
- 24 sequential windows across TRAIN (2024-02-20 to 2025-03-26, ~17 days each)
- Used a **no-trade baseline strategy** — infrastructure test only
- Result: 0/24 profitable windows, WF = 0.00
- Source: `docs/research/HYP-A-001_REAL_DATA_REPORT.md` lines 67-96

**WF-B (regime-conditional, CANDIDATE_GATE, 2026-10-08):**
- WF rate = 0.75 for HYP-A-001/TREND_UP/LONG
- Means 75% of walk-forward sub-windows within TRAIN showed positive net_mean for breakout LONG events in TREND_UP regime
- This is the metric cited when claiming "WF=0.75"
- Source: `docs/regime_research/CANDIDATE_GATE.md`, table row HYP-A-001/TREND_UP/LONG

**CRITICAL GAP**: The WF-B methodology is not fully documented. Missing:
- Total number of windows and window size for the regime-conditional WF
- Whether windows are rolling or non-overlapping
- The exact criterion for "profitable window" (positive mean? positive median? actual trading P&L?)
- If 9/12 windows = 0.75, removing 1 underperforming window changes verdict; if 18/24 = 0.75, more stable

### 3. Selection Bias

**Partial concern.** The regime-conditional study tested approximately 6 hypotheses × 5 regimes × 2 directions = 60 cells. Only 1 cell (HYP-A-001/TREND_UP/LONG) passed all 6 PRIMARY criteria.

Mitigating factors:
- Holm-Bonferroni correction applied (inter-cell multiple testing controlled)
- BBW_RANGE_THRESH (6%) selected by pre-registered criteria independent of strategy returns
- All rejected/fragile/inconclusive cells documented transparently (no file-drawer suppression)

Residual concern:
- It is not documented whether the regime-conditional analysis approach itself was pre-registered before computing results, or whether it was motivated by the weak unconditional result
- The DECISION.md says "WEAK — DO NOT ADVANCE" for the unconditional study. The decision to then run a regime-conditional analysis could constitute post-hoc conditioning on a weak result.

### 4. Sample Size and Effective n

- n=69 LONG breakout events in TREND_UP regime over 15-month TRAIN period (2736 H4 candles)
- Effective sample size is lower than 69 due to temporal autocorrelation (breakout events from the same trend segment are not independent)
- Bootstrap CI is used, which provides some robustness to autocorrelation, but no explicit block-bootstrap or autocorrelation correction is documented
- Source: `docs/regime_research/CANDIDATE_GATE.md` line 38; `docs/regime_research/TRAIN_REPORT.md` line 49

### 5. Lookahead

**VERIFIED: No lookahead in signal detection.**

From `hyp_a_001.py` lines 161-162:
```python
window = sorted_candles[i - lookback: i]   # strictly bars i-20..i-1
long_level = max(c.high for c in window)    # no bar i in window
```
Event registered at `candle[i].available_at` — after bar i closes.

**VERIFIED: No lookahead in regime detection.**

From `src/trading_engine/research/regime/detector.py` line 13: "All features at bar t use only close[0..t], OHLC[0..t]." EMA/ATR/BB computed causally (each value uses only past data). BBW_RANGE_THRESH = 6% applied to the same causal features.

No lookahead issue found.

### 6. Transaction Costs

**Partially covered.**

Included in net_proxy calculation:
- Taker fee: 0.055% per side
- Slippage estimate: 0.05% per side
- Net round-trip cost proxy: 0.21%

**Not included:**
- Funding (perpetual swap funding rate) — explicitly flagged in all reports
- For H32 (32×4h = 128h ≈ 5.3 days), funding accumulates across ~16 funding periods
- At typical BTC funding of 0.01% per 8h, 16 periods = ~0.16% additional cost
- This would reduce H32 net_proxy from +2.52% to ~+2.36% — still robustly positive
- For shorter horizons (H4 = 16h ≈ 2 funding periods ≈ 0.02%), impact is negligible

**Assessment**: Funding omission is a known risk but unlikely to reverse the H32 result given +2.52% net_proxy before funding.

### 7. CANDIDATE_GATE Criteria

| Criterion | Requirement | Actual | Pass |
|---|---|---|---|
| TRAIN verdict | SUPPORTED | SUPPORTED | YES |
| n | ≥ 50 | 69 | YES |
| net_mean | > 0 | +2.52% (H32) | YES |
| Bootstrap CI | excludes 0 | excl0 | YES |
| Holm-adjusted p | significant | p=0.001 (SIG) | YES |
| WF rate | ≥ 0.75 | **0.75 exactly** | YES (borderline) |

All 6 criteria pass. WF=0.75 is exactly at the minimum threshold — no margin.

Source: `docs/regime_research/CANDIDATE_GATE.md` lines 70-81

### 8. Reproducibility

**Strong.** Three independent hashes documented and cross-verified:
- Dataset hash: `e182346101e28d26` (consistent across all reports)
- Parameter hash (HYP-A-001): `d29a28f72e6fdcdb`
- Code version: `phase-7-step-7.2`
- Script: `scripts/run_regime_train.py` exists and is runnable
- Test suite: 961/961 PASSED (commit 30a6625)

Reproduced result is deterministic assuming same code version and dataset hash.

### 9. Temporal Ranges

| Split | Period | Candles | Status |
|---|---|---|---|
| TRAIN | 2024-01-01 → 2025-04-01 | 2736 | Used for hypothesis testing |
| VALIDATION | 2025-04-01 → 2025-10-01 | 1098 | **Untouched — clean** |
| OOS | 2025-10-01 → 2026-07-01 | 1638 | Untouched |
| HOLDOUT | 2026-07-01 → 2026-10-01 | 548 | Untouched |

VALIDATION period is clean and ready for use. No data contamination detected.

Source: `docs/research/HYP-A-001_REAL_DATA_REPORT.md` lines 17-23

### 10. Suspicious Patterns

**Two patterns warrant scrutiny:**

**a) WF=0.75 exactly at threshold**: Out of all tested combinations, the only PRIMARY candidate passes WF at exactly the gate minimum. This could be a genuine borderline result or an artifact. If the WF window count is small (e.g., 8 windows), a single window change flips the verdict.

**b) Methodological escalation after weak result**: The unconditional study produced WEAK verdict (EdgeVerdict.WEAK, WF=0/24). The decision in DECISION.md was "DO NOT ADVANCE TO OOS." The subsequent regime-conditional study (CANDIDATE_GATE) then found a passing combination. This sequence — weak unconditional → regime conditioning → one passing cell — resembles post-hoc slicing, even if controls (Holm, pre-registered BBW) were applied.

**Not flagged as fatal**: The CANDIDATE_GATE documentation is transparent, BBW threshold selection was genuinely pre-registered, and Holm correction addresses within-CANDIDATE_GATE multiple testing. But the inter-study escalation logic needs explicit documentation.

---

## Key Risks Before VALIDATION

### RISK 1 (BLOCKER): WF=0.75 methodology undocumented
The exact walk-forward methodology for the regime-conditional study (WF-B) is not documented in any report: number of windows, window size, overlap, definition of "profitable." Without this, the WF=0.75 value cannot be verified or reproduced as a standalone metric.

**Resolution required**: Document WF-B methodology in CANDIDATE_GATE or a supplementary note. Confirm: N windows total, X windows profitable.

### RISK 2 (BLOCKER): Unresolved conflict between DECISION.md and CANDIDATE_GATE.md
`docs/research/HYP-A-001_DECISION.md` states **"WEAK — DO NOT ADVANCE TO OOS"** and lists as a reason: "The research verdict is WEAK." This was written for the unconditional study.
`docs/regime_research/CANDIDATE_GATE.md` states **"PRIMARY CANDIDATE — eligible for VALIDATION"** based on the regime-conditional study.

These documents conflict without explicit reconciliation. A VALIDATION runner reading DECISION.md would conclude "don't advance." This ambiguity must be resolved with a superseding statement.

**Resolution required**: Add a note to DECISION.md (or create a reconciliation document) explicitly stating that the regime-conditional study supersedes the unconditional study for the TREND_UP/LONG cell, with the reasoning for methodological escalation.

### RISK 3 (MODERATE): Effective sample size and autocorrelation
n=69 events in TREND_UP/LONG over 15 months. In trending markets, consecutive breakouts in the same trend segment are correlated. Effective sample size may be lower. Bootstrap CI provides partial protection but no explicit block-bootstrap is documented.

**Resolution**: Accept as known risk, or add block-bootstrap confidence interval for VALIDATION planning.

### RISK 4 (LOW): Funding not in forward returns
Impact estimated at ~0.16% for H32 horizon. Net_proxy remains positive (+2.52% → ~+2.36%). Not a blocker for H32, but should be explicitly tracked in VALIDATION.

---

## Proposed VALIDATION Plan

If RISKS 1 and 2 are resolved:

**What to run**: `scripts/run_regime_train.py` equivalent on VALIDATION split (2025-04-01 → 2025-10-01, 1098 candles) with **no parameter changes** (param_hash must remain d29a28f72e6fdcdb, BBW=6%).

**Scope**: HYP-A-001/TREND_UP/LONG only. No expansion to other regime/direction cells unless pre-registered before VALIDATION run.

**Success criteria** (pre-register before running):
- Minimum: n ≥ 20 events (VALIDATION period is shorter)
- net_mean > 0
- Bootstrap CI should at minimum show positive median

**Failure criteria** (pre-register before running):
- net_mean ≤ 0, OR
- Fewer than 15 events (insufficient for any statistical inference)

**Strict rules**:
- Run once, report result regardless of outcome
- No parameter tuning after seeing VALIDATION result
- VALIDATION result cannot motivate changes to TRAIN parameters

**Data guard**: Verify dataset hash is `e182346101e28d26` before run; confirm VALIDATION split not previously loaded in any prior script run.

---

## Files Examined

| File | Role |
|---|---|
| `docs/research/HYP-A-001_REAL_DATA_REPORT.md` | Original unconditional event study result |
| `docs/research/HYP-A-001_DECISION.md` | Decision based on unconditional study: WEAK, no OOS |
| `docs/regime_research/CANDIDATE_GATE.md` | Regime-conditional classification; HYP-A-001/TREND_UP/LONG = PRIMARY |
| `docs/regime_research/TRAIN_REPORT.md` | Strategy × Regime verdict matrix, BBW=6% |
| `docs/regime_research/BBW_RANGE_THRESH_PREREGISTRATION.md` | Pre-registration of BBW threshold selection (6% = BBW p49) |
| `src/trading_engine/research/hypotheses/hyp_a_001.py` | Signal detector code; lookahead verified absent |
| `src/trading_engine/research/regime/detector.py` | Regime classifier; causal features verified |
| `src/trading_engine/research/walk_forward.py` | Walk-forward infrastructure |
| `scripts/run_regime_train.py` | Reproducibility entry point |
| `tests/unit/test_hyp_a_001.py` | Unit tests |
| `_step7_3_fix_backup_20261001_181532/HYP-A-001_REAL_DATA_REPORT.md.bak` | Backup of original report (identical to current) |
