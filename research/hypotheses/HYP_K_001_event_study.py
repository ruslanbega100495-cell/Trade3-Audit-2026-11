"""
HYP-K-001: MA Crossover — BTCUSDT H4 Direction Prediction (Event Study)

Pre-registered 2026-10-23. See research/registry/HYP-K-001.yaml for full spec.

EVENT STUDY ONLY — not a trading strategy backtest.
Positive result means signal has directional predictive power.
Does NOT prove profitable trading after fees, funding, or slippage.

Usage:
    python -m research.hypotheses.HYP_K_001_event_study --split train
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

# Pre-registered split boundaries (ISO date strings, inclusive start / exclusive end at open)
SPLITS = {
    "train":      ("2024-01-01", "2025-04-01"),
    "validation": ("2025-04-01", "2025-10-01"),
    "oos":        ("2025-10-01", "2026-07-01"),
}

# Pre-registered SMA sets
PRIMARY_SMA   = (20, 50)
EXPLORATORY_SMA = (35, 195)

# Pre-registered horizons (H4 candles)
PRIMARY_HORIZONS     = [8, 16]
EXPLORATORY_HORIZONS = [4, 32]
ALL_HORIZONS         = [4, 8, 16, 32]


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
    result = []
    for c in candles:
        ts = c["open_time"][:10]  # "YYYY-MM-DD"
        if start <= ts < end:
            result.append(c)
    return result


# ---------------------------------------------------------------------------
# SMA calculation (no lookahead: SMA[i] uses candles[i-period+1 .. i])
# ---------------------------------------------------------------------------

def compute_sma(closes: list[float], period: int) -> list[float | None]:
    sma = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        sma[i] = sum(closes[i - period + 1 : i + 1]) / period
    return sma


# ---------------------------------------------------------------------------
# Crossover detection
# ---------------------------------------------------------------------------

@dataclass
class CrossoverEvent:
    idx: int          # index of signal candle (close[t])
    direction: int    # +1 = golden cross (LONG), -1 = death cross (SHORT)


def find_crossovers(sma_fast: list[float | None], sma_slow: list[float | None]) -> list[CrossoverEvent]:
    events = []
    for i in range(1, len(sma_fast)):
        if sma_fast[i] is None or sma_slow[i] is None:
            continue
        if sma_fast[i - 1] is None or sma_slow[i - 1] is None:
            continue
        prev_diff = sma_fast[i - 1] - sma_slow[i - 1]
        curr_diff = sma_fast[i] - sma_slow[i]
        if prev_diff <= 0 and curr_diff > 0:
            events.append(CrossoverEvent(idx=i, direction=+1))  # golden cross
        elif prev_diff >= 0 and curr_diff < 0:
            events.append(CrossoverEvent(idx=i, direction=-1))  # death cross
    return events


# ---------------------------------------------------------------------------
# Direction-adjusted returns with non-overlapping window rule
# ---------------------------------------------------------------------------

def compute_returns(
    events: list[CrossoverEvent],
    opens: list[float],
    horizon: int,
    max_idx: int,
) -> tuple[list[float], int]:
    """
    Compute direction-adjusted returns for non-overlapping events.

    Returns:
        (list of direction_adjusted_returns, n_excluded_overlaps)

    Pre-registered rules:
    - entry = opens[t+1], exit = opens[t+1+H]
    - include event only if t+1+H <= max_idx (boundary rule)
    - non-overlapping: if event j < event i + H + 1, exclude j
    """
    included = []
    n_excluded = 0
    last_included_idx: int | None = None

    for ev in events:
        t = ev.idx
        entry_i = t + 1
        exit_i = t + 1 + horizon

        if exit_i > max_idx:
            n_excluded += 1
            continue

        if last_included_idx is not None and t < last_included_idx + horizon + 1:
            n_excluded += 1
            continue

        entry_price = opens[entry_i]
        exit_price = opens[exit_i]
        raw_return = (exit_price - entry_price) / entry_price
        direction_adj = ev.direction * raw_return
        included.append(direction_adj)
        last_included_idx = t

    return included, n_excluded


# ---------------------------------------------------------------------------
# Statistics (no scipy dependency: manual t-test)
# ---------------------------------------------------------------------------

def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def sample_std(xs: list[float]) -> float:
    m = mean(xs)
    variance = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(variance)


def t_stat(xs: list[float]) -> tuple[float, float]:
    """One-sample t-test vs mean=0. Returns (t, p_two_tailed) using t-distribution approx."""
    n = len(xs)
    if n < 2:
        return float("nan"), float("nan")
    m = mean(xs)
    s = sample_std(xs)
    t = m / (s / math.sqrt(n))
    # p-value using normal approximation (valid for n>=30; approximate for smaller)
    # Use simple z-to-p for reporting; note limitation for small n
    p = 2 * (1 - _norm_cdf(abs(t)))
    return t, p


def _norm_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def holm_bonferroni(p_values: list[float], alpha: float = 0.05) -> list[bool]:
    """Holm-Bonferroni correction. Returns list of reject-null booleans."""
    n = len(p_values)
    indexed = sorted(enumerate(p_values), key=lambda x: x[1])
    reject = [False] * n
    for rank, (orig_i, p) in enumerate(indexed):
        threshold = alpha / (n - rank)
        if p <= threshold:
            reject[orig_i] = True
        else:
            # once we fail to reject, all remaining tests also fail
            break
    return reject


# ---------------------------------------------------------------------------
# Core runner
# ---------------------------------------------------------------------------

def run_event_study(
    sma_params: tuple[int, int],
    horizons: list[int],
    candles_split: list[dict],
    label: str,
    is_primary: bool,
) -> list[dict]:
    fast_period, slow_period = sma_params
    closes = [float(c["close"]) for c in candles_split]
    opens  = [float(c["open"])  for c in candles_split]
    max_idx = len(opens) - 1

    sma_fast = compute_sma(closes, fast_period)
    sma_slow = compute_sma(closes, slow_period)
    events   = find_crossovers(sma_fast, sma_slow)

    n_total_signals = len(events)
    n_golden = sum(1 for e in events if e.direction == +1)
    n_death  = sum(1 for e in events if e.direction == -1)

    results = []
    p_values_for_holm = []
    horizon_results = {}

    for H in horizons:
        ret, n_excl = compute_returns(events, opens, H, max_idx)
        n = len(ret)
        if n < 5:
            t, p = float("nan"), float("nan")
        else:
            t, p = t_stat(ret)

        horizon_results[H] = {
            "sma": f"SMA({fast_period},{slow_period})",
            "horizon": H,
            "horizon_hours": H * 4,
            "n_events_total": n_total_signals,
            "n_golden_cross": n_golden,
            "n_death_cross": n_death,
            "n_included": n,
            "n_excluded_overlap_or_boundary": n_excl,
            "mean_dir_return_pct": round(mean(ret) * 100, 4) if ret else None,
            "std_pct": round(sample_std(ret) * 100, 4) if len(ret) >= 2 else None,
            "t_stat": round(t, 4) if not math.isnan(t) else None,
            "p_value": round(p, 6) if not math.isnan(p) else None,
            "is_primary": is_primary,
            "label": label,
            "holm_reject": None,  # filled below for primary
        }
        if is_primary:
            p_values_for_holm.append(p if not math.isnan(p) else 1.0)

    if is_primary and p_values_for_holm:
        rejects = holm_bonferroni(p_values_for_holm, alpha=0.05)
        for i, H in enumerate(horizons):
            horizon_results[H]["holm_reject"] = rejects[i]

    return list(horizon_results.values())


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_results(all_results: list[dict], split: str) -> None:
    print(f"\n{'='*70}")
    print(f"HYP-K-001 MA Crossover Event Study — SPLIT: {split.upper()}")
    print(f"{'='*70}")
    print(f"NOTE: Event study only. Positive result ≠ profitable strategy.\n")

    primary   = [r for r in all_results if r["is_primary"]]
    secondary = [r for r in all_results if not r["is_primary"]]

    print("PRIMARY SET (SMA(20,50), H=8 and H=16):")
    print(f"{'SMA':<12} {'H':>4} {'Hours':>6} {'N':>5} {'N_excl':>7} {'mean%':>8} {'t':>7} {'p':>8} {'Holm':>6}")
    print("-" * 70)
    for r in primary:
        holm_str = "REJECT" if r["holm_reject"] else "keep  "
        mean_str = f"{r['mean_dir_return_pct']:8.4f}" if r["mean_dir_return_pct"] is not None else "     n/a"
        t_str    = f"{r['t_stat']:7.3f}" if r["t_stat"] is not None else "    n/a"
        p_str    = f"{r['p_value']:8.6f}" if r["p_value"] is not None else "     n/a"
        print(f"{r['sma']:<12} {r['horizon']:>4} {r['horizon_hours']:>6} "
              f"{r['n_included']:>5} {r['n_excluded_overlap_or_boundary']:>7} "
              f"{mean_str} {t_str} {p_str} {holm_str}")

    any_primary_reject = any(r["holm_reject"] for r in primary if r["holm_reject"] is not None)
    all_primary_nan    = all(r["p_value"] is None for r in primary)

    print()
    if all_primary_nan:
        print("PRIMARY DECISION: INSUFFICIENT DATA (< 5 non-overlapping events)")
    elif any_primary_reject:
        print("PRIMARY DECISION: PROMISING — at least one primary test rejects H_null after Holm correction")
    else:
        print("PRIMARY DECISION: FAILS TO REJECT H_null — directional signal not statistically significant")
    print("(This is a TRAIN result only. Must validate on VALIDATION before acting.)")

    print(f"\n{'EXPLORATORY SET (results only — not used for primary decision)':}")
    print(f"{'SMA':<15} {'H':>4} {'Hours':>6} {'N':>5} {'N_excl':>7} {'mean%':>8} {'t':>7} {'p':>8}")
    print("-" * 70)
    for r in secondary:
        mean_str = f"{r['mean_dir_return_pct']:8.4f}" if r["mean_dir_return_pct"] is not None else "     n/a"
        t_str    = f"{r['t_stat']:7.3f}" if r["t_stat"] is not None else "    n/a"
        p_str    = f"{r['p_value']:8.6f}" if r["p_value"] is not None else "     n/a"
        print(f"{r['sma']:<15} {r['horizon']:>4} {r['horizon_hours']:>6} "
              f"{r['n_included']:>5} {r['n_excluded_overlap_or_boundary']:>7} "
              f"{mean_str} {t_str} {p_str}")

    print("\nLIMITATIONS:")
    print("  - Gross returns only: no taker fees (~5.5 bps/leg), no funding, no slippage")
    print("  - open[t+1] entry assumes instant fill at open price")
    print("  - p-values use normal approximation to t-distribution (valid n>=30)")
    print("  - Positive TRAIN result requires separate VALIDATION authorization before acting")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="HYP-K-001 MA Crossover Event Study")
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
    print(f"Split '{args.split}': {len(candles_split)} candles "
          f"({candles_split[0]['open_time'][:10]} to {candles_split[-1]['open_time'][:10]})")

    all_results = []

    # Primary set
    all_results.extend(run_event_study(
        PRIMARY_SMA, PRIMARY_HORIZONS, candles_split,
        label="PRIMARY", is_primary=True,
    ))

    # Exploratory: primary SMA, additional horizons
    all_results.extend(run_event_study(
        PRIMARY_SMA, [4, 32], candles_split,
        label="EXPLORATORY-A", is_primary=False,
    ))

    # Exploratory: secondary SMA set, all horizons
    all_results.extend(run_event_study(
        EXPLORATORY_SMA, ALL_HORIZONS, candles_split,
        label="EXPLORATORY-B", is_primary=False,
    ))

    print_results(all_results, args.split)


if __name__ == "__main__":
    main()
