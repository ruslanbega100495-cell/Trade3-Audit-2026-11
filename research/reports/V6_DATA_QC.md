# V6 Data QC Report — OI Series Sprint

**Date:** 2026-10-25
**Sprint:** K-006, K-007, K-008 (OI-based hypotheses)

---

## Datasets Verified

### 1. OHLCV — BTCUSDT H4
| Field         | Value |
|---------------|-------|
| File          | `research/datasets/raw/bybit/BTCUSDT/H4/2024-01-01_2026-09-30.json` |
| Records       | 6020 |
| Range         | 2024-01-01 to 2026-09-30 |
| Expected interval | 4h |
| Gaps > 6h     | **0** |
| Duplicates    | **0** |
| Stored hash   | `e182346101e28d26` |
| Hash verified | YES (matches stored field) |

### 2. Funding Rate — BTCUSDT 8h
| Field         | Value |
|---------------|-------|
| File          | `research/datasets/raw/bybit/BTCUSDT/funding/2024-01-01_2026-09-30.json` |
| Records       | 3012 |
| Range         | 2024-01-01 to 2026-09-30 |
| Expected interval | 8h |
| Gaps > 12h    | **0** |
| Duplicates    | **0** |
| Stored hash   | `5b8057d195a7c8a9` |
| Hash verified | YES |

### 3. Open Interest — BTCUSDT H4
| Field         | Value |
|---------------|-------|
| File          | `research/datasets/raw/bybit/BTCUSDT/H4/oi_2024-01-01_2026-09-30.json` |
| Records       | 6024 |
| Range         | 2024-01-01 to 2026-09-30 |
| Expected interval | 4h |
| Gaps > 6h     | **0** |
| Duplicates    | **0** |
| Computed hash | `eb1a3044ec0e3e35` |
| Format        | `{timestamp_ms: int, open_interest: float}` |

---

## OI / OHLCV Alignment

| Metric                   | Count |
|--------------------------|-------|
| OHLCV timestamps         | 6020  |
| OI timestamps            | 6024  |
| Inner join (both match)  | **6020** |
| Only in OHLCV (no OI)    | 0     |
| Only in OI (no OHLCV)    | 4     |

**Result:** Perfect alignment — all 6020 OHLCV bars have a matching OI bar.
The 4 OI-only records are the final bars of the dataset (2026-09-30 08:00, 12:00, 16:00 UTC and one more) where OHLCV coverage ends. This has no impact on TRAIN split (2024-01-01 to 2025-04-01).

---

## Summary

All three datasets are clean. No gaps, no duplicates, no alignment issues in TRAIN period.
Inner join approach used in K-007 and K-008 loses 0 bars in the TRAIN split.

---

## Scripts Used in This Sprint
- `research/hypotheses/HYP_K_006_event_study.py` — funding+OI alignment via `bisect_right`
- `research/hypotheses/HYP_K_007_event_study.py` — OI/OHLCV inner join
- `research/hypotheses/HYP_K_008_event_study.py` — OI/OHLCV inner join
