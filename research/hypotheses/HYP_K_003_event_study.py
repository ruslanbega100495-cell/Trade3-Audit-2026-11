"""
HYP-K-003: Fair Value Gap Fill — BTCUSDT H4 Event Study

Pre-registered 2026-10-24. See research/registry/HYP-K-003.yaml for full spec.

EVENT STUDY ONLY — not a trading strategy backtest.
Signal: 3-candle FVG forms, then price re-enters the gap zone within 50 bars.
Hypothesis: forward returns favor gap fill (continuation in gap direction).

Usage:
    python -m research.hypotheses.HYP_K_003_event_study --split train
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

DATA_FILE = Path(__file__).parent.parent / "datasets/raw/bybit/BTCUSDT/H4/2024-01-01_2026-09-30.json"
EXPECTED_HASH = "e182346101e28d26"

SPLITS = {
    "train":      ("2024-01-01", "2025-04-01"),
    "validation": ("2025-04-01", "2025-10-01"),
    "oos":        ("2025-10-01", "2026-07-01"),
}

ALL_HORIZONS = [4, 8, 16, 32]
FVG_EXPIRY = 50  # pre-registered; do not change after seeing results


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_candles() -> list[dict]:
    with open(DATA_FILE, encoding="utf-8") as f:
        data = json.load(f)
    if data.get("dataset_hash") != EXPECTED_HASH:
        raise ValueError(
            f"Data hash mismatch: expected {EXPECTED_HASH}, "
            f"got {data.get('dataset_hash')}. Do not proceed."
        )
    return data["candles"]


def filter_split(candles: list[dict], split: str) -> list[dict]:
    start, end = SPLITS[split]
    return [c for c in candles if start <= c["open_time"][:10] < end]


# ---------------------------------------------------------------------------
# Signal detection
# ---------------------------------------------------------------------------

@dataclass
class FVGEvent:
    idx: int        # j: signal bar (re-entry bar); entry = open[j+1]
    direction: int  # +1 = LONG (bullish FVG reentry), -1 = SHORT (bearish FVG reentry)


def find_events(candles: list[dict]) -> list[FVGEvent]:
    """
    Detect FVG re-entry events.

    Bearish FVG at bar t: high[t] < low[t-2]  (downward gap across t-1)
      gap zone: [high[t], low[t-2]]
      Signal j: first bar j in [t+1, t+50] where high[j] >= high[t]
      direction: SHORT (-1)

    Bullish FVG at bar t: low[t] > high[t-2]  (upward gap across t-1)
      gap zone: [high[t-2], low[t]]
      Signal j: first bar j in [t+1, t+50] where low[j] <= low[t]
      direction: LONG (+1)

    Requires t >= 2 (needs t-2 lookback).
    Each FVG produces at most ONE signal (first re-entry only).
    """
    highs  = [float(c["high"])  for c in candles]
    lows   = [float(c["low"])   for c in candles]
    n = len(candles)

    events: list[FVGEvent] = []

    for t in range(2, n):
        # --- Bearish FVG ---
        if highs[t] < lows[t - 2]:
            gap_top = lows[t - 2]   # gap zone upper bound
            gap_bot = highs[t]      # gap zone lower bound (high[t])
            # Signal: first j in [t+1, t+50] where high[j] >= gap_bot (re-enter from above)
            for j in range(t + 1, min(t + 1 + FVG_EXPIRY, n)):
                if highs[j] >= gap_bot:
                    # Boundary: j+1 must be valid index (entry at open[j+1])
                    if j + 1 < n:
                        events.append(FVGEvent(idx=j, direction=-1))
                    break  # only first re-entry

        # --- Bullish FVG ---
        if lows[t] > highs[t - 2]:
            gap_bot = highs[t - 2]  # gap zone lower bound
            gap_top = lows[t]       # gap zone upper bound (low[t])
            # Signal: first j in [t+1, t+50] where low[j] <= gap_top (re-enter from below)
            for j in range(t + 1, min(t + 1 + FVG_EXPIRY, n)):
                if lows[j] <= gap_top:
                    if j + 1 < n:
                        events.append(FVGEvent(idx=j, direction=+1))
                    break

    events.sort(key=lambda e: e.idx)
    return events


# ---------------------------------------------------------------------------
# Direction-adjusted returns with non-overlapping window rule
# ---------------------------------------------------------------------------

def compute_returns(
    events: list[FVGEvent],
    opens: list[float],
    horizon: int,
    max_idx: int,
) -> tuple[list[float], int]:
    """
    entry = opens[j+1], exit = opens[j+1+H]
    boundary: j+1+H <= max_idx
    non-overlapping per horizon: skip event if idx_j < last_included_idx + horizon + 1
    """
    included: list[float] = []
    n_excluded = 0
    last_included_idx: int | None = None

    for ev in events:
        j = ev.idx
        exit_i = j + 1 + horizon

        if exit_i > max_idx:
            n_excluded += 1
            continue

        if last_included_idx is not None and j < last_included_idx + horizon + 1:
            n_excluded += 1
            continue

        entry_price = opens[j + 1]
        exit_price  = opens[exit_i]
        raw_return  = (exit_price - entry_price) / entry_price
        direction_adj = ev.direction * raw_return
        included.append(direction_adj)
        last_included_idx = j

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


def t_stat(xs: list[float]) -> tuple[float, float]:
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
    events: list[FVGEvent],
    opens: list[float],
    horizons: list[int],
    max_idx: int,
) -> list[dict]:
    n_total = len(events)
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
            t, p = t_stat(ret)

        results.append({
            "horizon": H,
            "horizon_hours": H * 4,
            "n_events_total": n_total,
            "n_short_events": n_short,
            "n_long_events": n_long,
            "n_included": n,
            "n_excluded": n_excl,
            "mean_dir_return_pct": round(mean(ret) * 100, 4) if ret else None,
            "std_pct": round(sample_std(ret) * 100, 4) if len(ret) >= 2 else None,
            "t_stat": round(t, 4) if not math.isnan(t) else None,
            "p_value": round(p, 6) if not math.isnan(p) else None,
            "holm_reject": None,
        })
        p_values.append(p if not math.isnan(p) else 1.0)

    rejects = holm_bonferroni(p_values, alpha=0.05)
    for i, r in enumerate(results):
        r["holm_reject"] = rejects[i]

    return results


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_results(results: list[dict], split: str) -> None:
    print(f"\n{'='*72}")
    print(f"HYP-K-003 Fair Value Gap Fill — SPLIT: {split.upper()}")
    print(f"FVG_EXPIRY={FVG_EXPIRY} bars, horizons={ALL_HORIZONS}, Holm-Bonferroni alpha=0.05")
    print(f"{'='*72}")
    print(f"NOTE: Event study only. Positive result != profitable strategy.\n")

    if results:
        first = results[0]
        print(f"Total FVG re-entry events: "
              f"SHORT={first['n_short_events']}, LONG={first['n_long_events']}, "
              f"TOTAL={first['n_events_total']}\n")

    print(f"{'H':>4} {'Hours':>6} {'N_incl':>7} {'N_excl':>7} {'mean%':>8} {'std%':>7} "
          f"{'t':>7} {'p':>9} {'Holm':>8}")
    print("-" * 72)
    for r in results:
        mean_str = f"{r['mean_dir_return_pct']:8.4f}" if r["mean_dir_return_pct"] is not None else "     n/a"
        std_str  = f"{r['std_pct']:7.4f}" if r["std_pct"] is not None else "    n/a"
        t_str    = f"{r['t_stat']:7.3f}" if r["t_stat"] is not None else "    n/a"
        p_str    = f"{r['p_value']:9.6f}" if r["p_value"] is not None else "      n/a"
        holm_str = "REJECT" if r["holm_reject"] else "keep  "
        print(f"{r['horizon']:>4} {r['horizon_hours']:>6} {r['n_included']:>7} "
              f"{r['n_excluded']:>7} {mean_str} {std_str} {t_str} {p_str} {holm_str}")

    print()
    any_reject = any(r["holm_reject"] for r in results if r["holm_reject"] is not None)
    all_insuf  = all(r["p_value"] is None for r in results)

    if all_insuf:
        print("PRIMARY DECISION: INSUFFICIENT DATA (< 5 non-overlapping events per horizon)")
    elif any_reject:
        print("PRIMARY DECISION: PROMISING — at least one horizon rejects H_null after Holm")
    else:
        print("PRIMARY DECISION: FAILS TO REJECT H_null — no statistically significant FVG fill edge")
    print("(This is a TRAIN result only. Must validate on VALIDATION before acting.)")

    print("\nLIMITATIONS:")
    print("  - Gross returns only: no fees (~10.5 bps/leg), no funding, no slippage")
    print("  - open[j+1] entry assumes instant fill at open price")
    print("  - p-values use normal approximation (valid n>=30; approximate for smaller n)")
    print("  - FVG expiry 50 bars pre-registered; any change = new hypothesis")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="HYP-K-003 Fair Value Gap Fill Event Study")
    parser.add_argument("--split", choices=["train", "validation", "oos"], default="train")
    args = parser.parse_args()

    if args.split != "train":
        print(f"WARNING: Running on {args.split.upper()} requires separate authorization.")
        confirm = input("Type 'yes' to continue: ")
        if confirm.strip().lower() != "yes":
            print("Aborted.")
            sys.exit(0)

    print(f"Loading {DATA_FILE}...")
    candles_all = load_candles()
    print(f"Total candles: {len(candles_all)}. Hash verified: {EXPECTED_HASH}")

    candles_split = filter_split(candles_all, args.split)
    if not candles_split:
        print(f"ERROR: No candles found for split '{args.split}'.")
        sys.exit(1)
    print(f"Split '{args.split}': {len(candles_split)} candles "
          f"({candles_split[0]['open_time'][:10]} to {candles_split[-1]['open_time'][:10]})")

    events = find_events(candles_split)
    opens  = [float(c["open"]) for c in candles_split]
    max_idx = len(opens) - 1

    results = run_event_study(events, opens, ALL_HORIZONS, max_idx)
    print_results(results, args.split)


if __name__ == "__main__":
    main()
