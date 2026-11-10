# V6 OI Series Report — HYP-K-006, K-007, K-008

**Date:** 2026-10-25
**Researcher:** Ruslan
**Split:** TRAIN only (2024-01-01 / 2025-04-01)
**Status:** All three hypotheses REJECTED on TRAIN

---

## HYP-K-006 TRAIN Results
**Funding Extreme + OI Contraction**

N_events: SHORT=83, LONG=63, Total=146

| H | Hours | N_incl | N_excl | mean%   | t      | p        | Holm |
|---|-------|--------|--------|---------|--------|----------|------|
| 4 | 16    | 93     | 53     | -0.3075 | -1.544 | 0.122503 | keep |
| 8 | 32    | 75     | 71     | -0.2470 | -0.809 | 0.418215 | keep |
| 16| 64    | 55     | 91     | -0.2779 | -0.500 | 0.616749 | keep |
| 32| 128   | 37     | 109    | +0.4246 | +0.424 | 0.671854 | keep |

**Decision: REJECTED**

Notes:
- OI contraction filter halved events vs G-001 (146 vs 318)
- Negative mean at H=4/8/16 is in hypothesized SHORT direction but far below significance
- Adding OI filter to G-001 did not rescue the funding extreme signal

---

## HYP-K-007 TRAIN Results
**OI Absolute Level Extremes**

N_aligned_bars: 2736, N_events: SHORT=392, LONG=415, Total=807

| H | Hours | N_incl | N_excl | mean%   | t      | p        | Holm |
|---|-------|--------|--------|---------|--------|----------|------|
| 4 | 16    | 198    | 609    | +0.0469 | +0.303 | 0.761662 | keep |
| 8 | 32    | 122    | 685    | +0.1016 | +0.378 | 0.705293 | keep |
| 16| 64    | 73     | 734    | +0.1281 | +0.335 | 0.737643 | keep |
| 32| 128   | 45     | 762    | -0.2299 | -0.276 | 0.782856 | keep |

**Decision: REJECTED**

Note on OI non-stationarity (pre-registered limitation observed):
807 events from 2336 signal-eligible bars = 34.5% signal rate. Expected ~20%
(10% SHORT + 10% LONG from deciles). The elevated rate confirms OI level is trending:
rolling percentile clusters many consecutive bars as "extreme high" or "extreme low"
because the OI series drifts. This is a fundamental limitation of level-based signals
on non-stationary series. Confirmed as observed.

---

## HYP-K-008 TRAIN Results
**Price/OI Divergence (Close Breakout + OI Contraction)**

N_aligned_bars: 2736, N_events: SHORT=115, LONG=110, Total=225

| H | Hours | N_incl | N_excl | mean%   | t      | p        | Holm |
|---|-------|--------|--------|---------|--------|----------|------|
| 4 | 16    | 134    | 91     | -0.1399 | -0.714 | 0.475173 | keep |
| 8 | 32    | 108    | 117    | -0.4622 | -1.727 | 0.084104 | keep |
| 16| 64    | 84     | 141    | -0.7758 | -1.549 | 0.121278 | keep |
| 32| 128   | 53     | 172    | -0.2776 | -0.378 | 0.705602 | keep |

**Decision: REJECTED**

Closest result: H=8 p=0.084 (not significant after Holm, alpha threshold = 0.05/4 = 0.0125
for rank-1 hypothesis). The negative mean_dir_return at H=4/8/16 is the OPPOSITE of the
hypothesized direction: price tends to continue slightly rather than reverse after a
close breakout with OI contraction. Effect is small, inconsistent across horizons,
and does not survive correction. Do NOT act on this.

---

## Data QC Summary

| Dataset        | Records | Gaps | Dups | Hash               |
|----------------|---------|------|------|--------------------|
| OHLCV H4       | 6020    | 0    | 0    | e182346101e28d26 ✓ |
| Funding 8h     | 3012    | 0    | 0    | 5b8057d195a7c8a9 ✓ |
| OI H4          | 6024    | 0    | 0    | eb1a3044ec0e3e35   |

OI/OHLCV alignment: 6020/6020 OHLCV bars matched. 4 trailing OI-only bars
(2026-09-30 08:00–16:00) with no OHLCV match — no impact on TRAIN split.

---

## New Files Created

**Registry:**
- `research/registry/HYP-K-006.yaml`
- `research/registry/HYP-K-007.yaml`
- `research/registry/HYP-K-008.yaml`

**Scripts:**
- `research/hypotheses/HYP_K_006_event_study.py`
- `research/hypotheses/HYP_K_007_event_study.py`
- `research/hypotheses/HYP_K_008_event_study.py`

**Reports:**
- `research/reports/V6_DATA_QC.md`
- `research/reports/V6_OI_SERIES_REPORT.md` (this file)

---

## Git Status (untracked only)

All 8 files above are untracked (new). No tracked files were modified.

---

## Safety Checklist

| Check                              | Status |
|------------------------------------|--------|
| TRADING_DISABLED=True              | not modified — confirmed |
| OOS/HOLDOUT run                    | NOT run |
| VALIDATION run                     | NOT run |
| Tracked files modified             | NO |
| git commit/push                    | NO |
| scipy used                         | NO — stdlib + pandas + numpy only |

---

## Sprint Summary

All three OI-based hypotheses REJECTED on TRAIN.

- **K-006** (Funding + OI contraction): OI filter did not rescue G-001. 146 events,
  direction consistent with hypothesis at short horizons but nowhere near p<0.05.

- **K-007** (OI level extremes): Confirmed pre-registered non-stationarity concern.
  Elevated signal rate (34.5% vs expected 20%) shows rolling percentile is clustering.
  t-stats near zero, no directional edge observed.

- **K-008** (Price breakout + OI divergence): Most interesting result in this sprint.
  H=8 p=0.084 is the closest to significance, but the sign is NEGATIVE — meaning
  the signal may weakly anti-predict. Breakout + OI contraction appears to continue
  slightly rather than reverse. Not significant, not actionable.

**Next steps (optional):** Consider testing continuation hypothesis: breakout + OI contraction
as LONG (not reversal) — but this would be a NEW pre-registered hypothesis, not K-008.
