"""
HYP-K-008: Price/OI Divergence (Close Breakout + OI Contraction) — BTCUSDT H4 Event Study

Pre-registered 2026-10-25. See research/registry/HYP-K-008.yaml for full spec.

Mechanism:
  SHORT: close[t] > max(close[t-20:t]) AND OI[t] - OI[t-4] < 0
    => Confirmed close breakout without OI growth = distribution into retail chase.
  LONG: close[t] < min(close[t-20:t]) AND OI[t] - OI[t-4] < 0
    => Confirmed close breakdown without OI growth = capitulation / forced short closures.

Differs from K-002: K-002 is intrabar sweep (high>prev_high, close<prev_high).
K-008 is confirmed close breakout (close > max of prior N closes).

Usage:
    python -m research.hypotheses.HYP_K_008_event_study --split train
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

OI_FILE    = Path(__file__).parent.parent / "datasets/raw/bybit/BTCUSDT/H4/oi_2024-01-01_2026-09-30.json"
OHLCV_FILE = Path(__file__).parent.parent / "datasets/raw/bybit/BTCUSDT/H4/2024-01-01_2026-09-30.json"

OHLCV_HASH   = "e182346101e28d26"
N_LOOKBACK   = 20   # pre-registered; do not change after seeing results
ALL_HORIZONS = [4, 8, 16, 32]

SPLITS = {
    "train":      ("2024-01-01", "2025-04-01"),
    "validation": ("2025-04-01", "2025-10-01"),
    "oos":        ("2025-10-01", "2026-07-01"),
}


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def iso_to_ms(iso_str: str) -> int:
    s = iso_str
    if s.endswith("+00:00"):
        s = s[:-6]
    elif s.endswith("Z"):
        s = s[:-1]
    if len(s) == 10:
        s = s + "T00:00:00"
    dt = datetime(
        int(s[0:4]), int(s[5:7]), int(s[8:10]),
        int(s[11:13]), int(s[14:16]), int(s[17:19]),
        tzinfo=timezone.utc,
    )
    return int(dt.timestamp() * 1000)


# ---------------------------------------------------------------------------
# Data loading and alignment
# ---------------------------------------------------------------------------

def load_oi() -> list[dict]:
    with open(OI_FILE, encoding="utf-8") as f:
        d = json.load(f)
    return d["records"]


def load_ohlcv() -> list[dict]:
    with open(OHLCV_FILE, encoding="utf-8") as f:
        d = json.load(f)
    if d.get("dataset_hash") != OHLCV_HASH:
        raise ValueError(
            f"OHLCV hash mismatch: stored={d.get('dataset_hash')} expected={OHLCV_HASH}"
        )
    candles = d["candles"]
    for c in candles:
        c["ts_ms"] = iso_to_ms(c["open_time"])
    return candles


def align_oi_ohlcv(oi_all: list[dict], ohlcv_all: list[dict]) -> list[dict]:
    """Inner join OI and OHLCV on timestamp_ms. Sorted ascending."""
    ohlcv_by_ts = {c["ts_ms"]: c for c in ohlcv_all}
    aligned = []
    for r in oi_all:
        ts = r["timestamp_ms"]
        if ts in ohlcv_by_ts:
            c = ohlcv_by_ts[ts]
            aligned.append({
                "ts_ms":     ts,
                "open_time": c["open_time"],
                "open":      float(c["open"]),
                "close":     float(c["close"]),
                "oi":        r["open_interest"],
            })
    aligned.sort(key=lambda x: x["ts_ms"])
    return aligned


def filter_aligned_split(aligned: list[dict], split: str) -> list[dict]:
    start_ms = iso_to_ms(SPLITS[split][0])
    end_ms   = iso_to_ms(SPLITS[split][1])
    return [r for r in aligned if start_ms <= r["ts_ms"] < end_ms]


# ---------------------------------------------------------------------------
# Signal detection
# ---------------------------------------------------------------------------

@dataclass
class DivergenceEvent:
    idx: int       # signal bar index in aligned_train
    direction: int # -1=SHORT (breakout+OI fall), +1=LONG (breakdown+OI fall)


def find_events(aligned_train: list[dict]) -> list[DivergenceEvent]:
    """
    At bar t:
      rolling_max = max(close[t-N:t])  — excludes t
      rolling_min = min(close[t-N:t])  — excludes t
      oi_delta    = OI[t] - OI[t-4]    — requires t >= 4

    SHORT: close[t] > rolling_max AND oi_delta < 0
    LONG:  close[t] < rolling_min AND oi_delta < 0

    Requires t >= max(N_LOOKBACK, 4) = 20.

    Lookahead check:
      close[t]: candle closed [OK]
      max(close[t-N:t]): only prior bars [OK]
      OI[t]: same bar, assumed known at bar close [OK]
      entry: open[t+1] — strictly next bar [OK]
    """
    closes = [r["close"] for r in aligned_train]
    ois    = [r["oi"]    for r in aligned_train]

    events: list[DivergenceEvent] = []

    for t in range(N_LOOKBACK, len(aligned_train)):
        if t < 4:
            continue  # need 4 prior OI bars (already satisfied by N_LOOKBACK=20)

        rolling_max = max(closes[t - N_LOOKBACK : t])
        rolling_min = min(closes[t - N_LOOKBACK : t])
        oi_delta    = ois[t] - ois[t - 4]
        close_t     = closes[t]

        if close_t > rolling_max and oi_delta < 0:
            events.append(DivergenceEvent(idx=t, direction=-1))  # SHORT

        if close_t < rolling_min and oi_delta < 0:
            events.append(DivergenceEvent(idx=t, direction=+1))  # LONG

    # Note: SHORT and LONG are mutually exclusive (close can't be both > max and < min)
    events.sort(key=lambda e: e.idx)
    return events


# ---------------------------------------------------------------------------
# Returns with non-overlapping window
# ---------------------------------------------------------------------------

def compute_returns(
    events: list[DivergenceEvent],
    opens: list[float],
    horizon: int,
    max_idx: int,
) -> tuple[list[float], int]:
    """
    Entry: opens[ev.idx + 1]
    Exit:  opens[ev.idx + 1 + H]
    Non-overlapping by signal bar index.
    """
    included: list[float] = []
    n_excluded = 0
    last_t: int | None = None

    for ev in events:
        entry_i = ev.idx + 1
        exit_i  = entry_i + horizon

        if exit_i > max_idx:
            n_excluded += 1
            continue

        if last_t is not None and ev.idx < last_t + horizon + 1:
            n_excluded += 1
            continue

        raw_ret = (opens[exit_i] - opens[entry_i]) / opens[entry_i]
        included.append(ev.direction * raw_ret)
        last_t = ev.idx

    return included, n_excluded


# ---------------------------------------------------------------------------
# Statistics (stdlib only)
# ---------------------------------------------------------------------------

def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def sample_std(xs: list[float]) -> float:
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _norm_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def t_test(xs: list[float]) -> tuple[float, float]:
    n = len(xs)
    if n < 2:
        return float("nan"), float("nan")
    m = mean(xs)
    s = sample_std(xs)
    t = m / (s / math.sqrt(n))
    p = 2 * (1 - _norm_cdf(abs(t)))
    return t, p


def holm_bonferroni(p_values: list[float], alpha: float = 0.05) -> list[bool]:
    n = len(p_values)
    indexed = sorted(enumerate(p_values), key=lambda x: x[1])
    reject = [False] * n
    for rank, (orig_i, p) in enumerate(indexed):
        threshold = alpha / (n - rank)
        if p <= threshold:
            reject[orig_i] = True
        else:
            break
    return reject


# ---------------------------------------------------------------------------
# Core runner
# ---------------------------------------------------------------------------

def run_event_study(
    events: list[DivergenceEvent],
    opens: list[float],
    horizons: list[int],
    max_idx: int,
) -> list[dict]:
    n_short = sum(1 for e in events if e.direction == -1)
    n_long  = sum(1 for e in events if e.direction == +1)

    results: list[dict] = []
    p_values: list[float] = []

    for H in horizons:
        ret, n_excl = compute_returns(events, opens, H, max_idx)
        n = len(ret)
        if n < 5:
            t, p = float("nan"), float("nan")
        else:
            t, p = t_test(ret)

        results.append({
            "horizon": H,
            "horizon_hours": H * 4,
            "n_short": n_short,
            "n_long": n_long,
            "n_included": n,
            "n_excluded": n_excl,
            "mean_dir_return_pct": round(mean(ret) * 100, 4) if ret else None,
            "std_pct": round(sample_std(ret) * 100, 4) if len(ret) >= 2 else None,
            "t_stat": round(t, 4) if not math.isnan(t) else None,
            "p_value": round(p, 6) if not math.isnan(p) else None,
            "holm_reject": None,
        })
        p_values.append(p if not math.isnan(p) else 1.0)

    rejects = holm_bonferroni(p_values)
    for i, r in enumerate(results):
        r["holm_reject"] = rejects[i]

    return results


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_results(results: list[dict], split: str, n_aligned_total: int) -> None:
    n_short = results[0]["n_short"] if results else 0
    n_long  = results[0]["n_long"]  if results else 0

    print(f"\n{'='*72}")
    print(f"HYP-K-008 Price/OI Divergence — SPLIT: {split.upper()}")
    print(f"N_lookback={N_LOOKBACK}, horizons={ALL_HORIZONS}, Holm-Bonferroni alpha=0.05")
    print(f"{'='*72}")
    print(f"Aligned bars in split: {n_aligned_total}")
    print(f"Signal events: SHORT={n_short} (close>max+OI fall), LONG={n_long} (close<min+OI fall)\n")

    print(f"{'H':>4} {'Hours':>6} {'N_incl':>7} {'N_excl':>7} {'mean%':>8} {'std%':>7} "
          f"{'t':>7} {'p':>9} {'Holm':>8}")
    print("-" * 72)
    for r in results:
        mean_s = f"{r['mean_dir_return_pct']:8.4f}" if r["mean_dir_return_pct"] is not None else "     n/a"
        std_s  = f"{r['std_pct']:7.4f}"             if r["std_pct"] is not None else "    n/a"
        t_s    = f"{r['t_stat']:7.3f}"              if r["t_stat"] is not None else "    n/a"
        p_s    = f"{r['p_value']:9.6f}"             if r["p_value"] is not None else "      n/a"
        holm_s = "REJECT" if r["holm_reject"] else "keep  "
        print(f"{r['horizon']:>4} {r['horizon_hours']:>6} {r['n_included']:>7} "
              f"{r['n_excluded']:>7} {mean_s} {std_s} {t_s} {p_s} {holm_s}")

    print()
    any_reject = any(r["holm_reject"] for r in results if r["holm_reject"] is not None)
    if any_reject:
        print("PRIMARY DECISION: PROMISING — at least one horizon rejects H_null after Holm")
    else:
        print("PRIMARY DECISION: FAILS TO REJECT H_null — no statistically significant edge")
    print("(TRAIN result only. Must validate on VALIDATION before acting.)")
    print("\nLIMITATIONS:")
    print("  - Gross returns only: no fees (~5.5 bps/leg), no funding cost, no slippage")
    print("  - Both branches use OI_delta < 0 but opposite directions (correct per mechanism)")
    print("  - SHORT and LONG branches NOT separated post-hoc")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="HYP-K-008 Price/OI Divergence Event Study")
    parser.add_argument("--split", choices=["train", "validation", "oos"], default="train")
    args = parser.parse_args()

    if args.split != "train":
        print(f"WARNING: Running on {args.split.upper()} requires separate authorization.")
        confirm = input("Type 'yes' to continue: ")
        if confirm.strip().lower() != "yes":
            print("Aborted.")
            sys.exit(0)

    print(f"Loading OI ({OI_FILE.name})...")
    oi_all = load_oi()
    print(f"  {len(oi_all)} records.")

    print(f"Loading OHLCV ({OHLCV_FILE.name})...")
    ohlcv_all = load_ohlcv()
    print(f"  {len(ohlcv_all)} candles. Hash verified: {OHLCV_HASH}")

    print("Aligning OI and OHLCV (inner join on timestamp_ms)...")
    aligned_all = align_oi_ohlcv(oi_all, ohlcv_all)
    print(f"  {len(aligned_all)} aligned bars (OI={len(oi_all)}, OHLCV={len(ohlcv_all)})")

    aligned_split = filter_aligned_split(aligned_all, args.split)
    print(f"Split '{args.split}': {len(aligned_split)} aligned bars "
          f"({aligned_split[0]['open_time'][:10]} to {aligned_split[-1]['open_time'][:10]})")

    opens   = [r["open"] for r in aligned_split]
    max_idx = len(opens) - 1

    print("Finding price/OI divergence events...")
    events = find_events(aligned_split)
    n_short = sum(1 for e in events if e.direction == -1)
    n_long  = sum(1 for e in events if e.direction == +1)
    print(f"  Found {len(events)} events (SHORT={n_short}, LONG={n_long})")

    results = run_event_study(events, opens, ALL_HORIZONS, max_idx)
    print_results(results, args.split, len(aligned_split))


if __name__ == "__main__":
    main()
