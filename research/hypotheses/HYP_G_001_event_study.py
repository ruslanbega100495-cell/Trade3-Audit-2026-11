"""
HYP-G-001: Funding Rate Extreme Reversal -- BTCUSDT H4 Event Study
Pre-registered 2026-10-25. See research/registry/HYP-G-001.yaml for full spec.

EVENT STUDY ONLY -- not a trading strategy backtest.
Signal: when BTCUSDT 8h funding rate is in the top/bottom 10% of its rolling
        400-period history, forward H4 returns favor reversal.
Hypothesis: forward direction-adjusted returns are positive (H_null = 0).

Usage:
    python -m research.hypotheses.HYP_G_001_event_study --split train
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

FUNDING_FILE = Path(__file__).parent.parent / "datasets/raw/bybit/BTCUSDT/funding/2024-01-01_2026-09-30.json"
OHLCV_FILE   = Path(__file__).parent.parent / "datasets/raw/bybit/BTCUSDT/H4/2024-01-01_2026-09-30.json"
OHLCV_HASH   = "e182346101e28d26"
FUNDING_HASH = "5b8057d195a7c8a9"

SPLITS = {
    "train":      ("2024-01-01", "2025-04-01"),
    "validation": ("2025-04-01", "2025-10-01"),
    "oos":        ("2025-10-01", "2026-07-01"),
}
ALL_HORIZONS   = [4, 8, 16, 32]
ROLLING_WINDOW = 400
PERCENTILE_HIGH = 90
PERCENTILE_LOW  = 10


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_ohlcv() -> list[dict]:
    with open(OHLCV_FILE, encoding="utf-8") as f:
        d = json.load(f)
    if d.get("dataset_hash") != OHLCV_HASH:
        raise ValueError(f"OHLCV hash mismatch: expected {OHLCV_HASH}, got {d.get('dataset_hash')}")
    return d["candles"]


def load_funding() -> list[dict]:
    with open(FUNDING_FILE, encoding="utf-8") as f:
        d = json.load(f)
    if d.get("dataset_hash") != FUNDING_HASH:
        raise ValueError(f"Funding hash mismatch: expected {FUNDING_HASH}, got {d.get('dataset_hash')}")
    return d["records"]


def filter_candles_split(candles: list[dict], split: str) -> list[dict]:
    start, end = SPLITS[split]
    return [c for c in candles if start <= c["open_time"][:10] < end]


# ---------------------------------------------------------------------------
# Statistics (stdlib only)
# ---------------------------------------------------------------------------

def percentile(values: list[float], p: float) -> float:
    """Linear interpolation percentile."""
    s = sorted(values)
    n = len(s)
    if n == 0:
        return float("nan")
    idx = (p / 100) * (n - 1)
    lo, hi = int(idx), min(int(idx) + 1, n - 1)
    return s[lo] + (s[hi] - s[lo]) * (idx - lo)


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
# Signal detection
# ---------------------------------------------------------------------------

@dataclass
class FundingEvent:
    idx: int       # index in candles_split
    direction: int # +1 LONG, -1 SHORT


def find_events(candles_split: list[dict], funding_all: list[dict], split: str) -> list[FundingEvent]:
    """
    For each funding record in the given split period where the rate is extreme
    (top/bottom 10% of rolling 400-period window), find the first H4 candle
    with open_time >= funding_timestamp. That candle is the entry candle.

    Warmup: requires 400 funding observations before first valid signal.
    Deduplication: if multiple funding events map to same candle, keep first.
    """
    split_start, split_end = SPLITS[split]

    # Build sorted list of H4 candle open_time keys (truncated to minute)
    ohlcv_times = [c["open_time"][:16] for c in candles_split]  # "YYYY-MM-DDTHH:MM"
    ohlcv_time_to_idx = {t: i for i, t in enumerate(ohlcv_times)}

    # All funding sorted ascending
    funding_sorted = sorted(funding_all, key=lambda r: r["timestamp_ms"])

    events: list[FundingEvent] = []

    for j, rec in enumerate(funding_sorted):
        # Only produce signals within the split window
        if rec["timestamp_iso"][:10] < split_start:
            continue
        if rec["timestamp_iso"][:10] >= split_end:
            break

        # Need at least ROLLING_WINDOW prior observations
        # Count how many funding records exist strictly before this one
        if j < ROLLING_WINDOW:
            continue

        window_rates = [funding_sorted[k]["funding_rate"] for k in range(j - ROLLING_WINDOW, j)]
        q90 = percentile(window_rates, PERCENTILE_HIGH)
        q10 = percentile(window_rates, PERCENTILE_LOW)
        fr = rec["funding_rate"]

        if fr >= q90:
            direction = -1  # SHORT — extreme positive funding, expect reversal
        elif fr <= q10:
            direction = +1  # LONG — extreme negative funding, expect reversal
        else:
            continue

        # Find first H4 candle with open_time >= funding timestamp (ISO prefix match)
        fund_key = rec["timestamp_iso"][:16]  # "YYYY-MM-DDTHH:MM"
        idx_in_sorted = bisect.bisect_left(ohlcv_times, fund_key)
        if idx_in_sorted >= len(ohlcv_times):
            continue  # beyond end of split candles
        events.append(FundingEvent(idx=idx_in_sorted, direction=direction))

    # Sort by candle index; deduplicate (first funding event wins per candle)
    events.sort(key=lambda e: e.idx)
    seen_idx: set[int] = set()
    unique: list[FundingEvent] = []
    for ev in events:
        if ev.idx not in seen_idx:
            unique.append(ev)
            seen_idx.add(ev.idx)
    return unique


# ---------------------------------------------------------------------------
# Returns computation
# ---------------------------------------------------------------------------

def compute_returns(
    events: list[FundingEvent],
    opens: list[float],
    horizon: int,
    max_idx: int,
) -> tuple[list[float], int]:
    """
    entry = opens[idx], exit = opens[idx + H]
    Non-overlapping on idx values.
    """
    included: list[float] = []
    n_excluded = 0
    last_included_idx: int | None = None

    for ev in events:
        idx = ev.idx
        exit_i = idx + horizon

        if exit_i > max_idx:
            n_excluded += 1
            continue

        if last_included_idx is not None and idx < last_included_idx + horizon + 1:
            n_excluded += 1
            continue

        entry_price = opens[idx]
        exit_price  = opens[exit_i]
        raw_return  = (exit_price - entry_price) / entry_price
        direction_adj = ev.direction * raw_return
        included.append(direction_adj)
        last_included_idx = idx

    return included, n_excluded


# ---------------------------------------------------------------------------
# Core runner
# ---------------------------------------------------------------------------

def run_event_study(
    events: list[FundingEvent],
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
    print(f"HYP-G-001 Funding Rate Extreme Reversal -- SPLIT: {split.upper()}")
    print(f"rolling_window={ROLLING_WINDOW}, percentiles=[{PERCENTILE_LOW},{PERCENTILE_HIGH}], "
          f"horizons={ALL_HORIZONS}, Holm-Bonferroni alpha=0.05")
    print(f"{'='*72}")
    print(f"NOTE: Event study only. Positive result != profitable strategy.\n")

    if results:
        first = results[0]
        print(f"Total funding extreme events: "
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
        print("PRIMARY DECISION: PROMISING -- at least one horizon rejects H_null after Holm")
    else:
        print("PRIMARY DECISION: FAILS TO REJECT H_null -- no statistically significant funding edge")
    print("(This is a TRAIN result only. Must validate on VALIDATION before acting.)")

    print("\nLIMITATIONS:")
    print("  - Gross returns only: no fees (~10.5 bps/leg), no funding, no slippage")
    print("  - 8h funding aligned to H4 open -- 1 funding event may map to 2 H4 candles")
    print("  - p-values use normal approximation (valid n>=30; approximate for smaller n)")
    print("  - rolling_window=400 is pre-registered; changing it = new hypothesis")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="HYP-G-001 Funding Rate Extreme Reversal Event Study")
    parser.add_argument("--split", choices=["train", "validation", "oos"], default="train")
    args = parser.parse_args()

    if args.split != "train":
        print(f"WARNING: Running on {args.split.upper()} requires separate authorization.")
        confirm = input("Type 'yes' to continue: ")
        if confirm.strip().lower() != "yes":
            print("Aborted.")
            sys.exit(0)

    print(f"Loading OHLCV: {OHLCV_FILE}...")
    candles_all = load_ohlcv()
    print(f"Total OHLCV candles: {len(candles_all)}. Hash verified: {OHLCV_HASH}")

    print(f"Loading funding: {FUNDING_FILE}...")
    funding_all = load_funding()
    print(f"Total funding records: {len(funding_all)}. Hash verified: {FUNDING_HASH}")

    candles_split = filter_candles_split(candles_all, args.split)
    if not candles_split:
        print(f"ERROR: No candles found for split '{args.split}'.")
        sys.exit(1)
    print(f"Split '{args.split}': {len(candles_split)} candles "
          f"({candles_split[0]['open_time'][:10]} to {candles_split[-1]['open_time'][:10]})")

    events = find_events(candles_split, funding_all, args.split)
    opens  = [float(c["open"]) for c in candles_split]
    max_idx = len(opens) - 1

    results = run_event_study(events, opens, ALL_HORIZONS, max_idx)
    print_results(results, args.split)


if __name__ == "__main__":
    main()
