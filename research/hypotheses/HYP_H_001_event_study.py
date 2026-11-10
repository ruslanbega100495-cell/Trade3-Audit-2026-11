"""
HYP-H-001: Basis Extreme Reversal -- BTCUSDT H4 Event Study
Pre-registered 2026-10-25. See research/registry/HYP-H-001.yaml for full spec.

EVENT STUDY ONLY -- not a trading strategy backtest.
Signal: when BTCUSDT H4 basis (perp_close - spot_close) / spot_close * 100
        is in the top/bottom 10% of rolling 400-bar history, forward perp
        returns favor reversal.
Hypothesis: forward direction-adjusted returns are positive (H_null = 0).

Usage:
    python -m research.hypotheses.HYP_H_001_event_study --split train
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

PERP_FILE  = Path(__file__).parent.parent / "datasets/raw/bybit/BTCUSDT/H4/2024-01-01_2026-09-30.json"
SPOT_FILE  = Path(__file__).parent.parent / "datasets/raw/bybit/BTCUSDT/H4_spot/2024-01-01_2026-09-30.json"
PERP_HASH  = "e182346101e28d26"
SPOT_HASH  = "952907069c60e356"

SPLITS = {
    "train":      ("2024-01-01", "2025-04-01"),
    "validation": ("2025-04-01", "2025-10-01"),
    "oos":        ("2025-10-01", "2026-07-01"),
}
ALL_HORIZONS    = [4, 8, 16, 32]
ROLLING_WINDOW  = 400
PERCENTILE_HIGH = 90
PERCENTILE_LOW  = 10


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_candles(filepath: Path, expected_hash: str) -> list[dict]:
    with open(filepath, encoding="utf-8") as f:
        d = json.load(f)
    if d.get("dataset_hash") != expected_hash:
        raise ValueError(f"Hash mismatch in {filepath}: expected {expected_hash}, got {d.get('dataset_hash')}")
    return d["candles"]


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
class BasisEvent:
    idx: int       # index in aligned perp candles array
    direction: int # +1 LONG, -1 SHORT


def build_aligned_series(
    perp_candles: list[dict],
    spot_candles: list[dict],
    split: str,
) -> tuple[list[dict], list[float]]:
    """
    Inner join perp and spot on open_time (minute-level prefix match).
    Returns (aligned_perp_candles, basis_series).
    """
    split_start, split_end = SPLITS[split]

    spot_by_time = {
        c["open_time"][:16]: float(c["close"])
        for c in spot_candles
        if split_start <= c["open_time"][:10] < split_end
    }

    aligned_perp: list[dict] = []
    basis: list[float] = []

    for c in perp_candles:
        if not (split_start <= c["open_time"][:10] < split_end):
            continue
        key = c["open_time"][:16]
        if key not in spot_by_time:
            continue
        perp_close = float(c["close"])
        spot_close = spot_by_time[key]
        b = (perp_close - spot_close) / spot_close * 100
        aligned_perp.append(c)
        basis.append(b)

    return aligned_perp, basis


def find_events(
    aligned_perp: list[dict],
    basis: list[float],
) -> list[BasisEvent]:
    """
    At each bar i >= ROLLING_WINDOW, compute rolling percentile of
    basis[i-400:i] (excludes current bar to avoid lookahead).
    Signal at bar i -> entry at bar i+1.
    """
    events: list[BasisEvent] = []

    for i in range(ROLLING_WINDOW, len(basis)):
        window = basis[i - ROLLING_WINDOW:i]
        q90 = percentile(window, PERCENTILE_HIGH)
        q10 = percentile(window, PERCENTILE_LOW)
        b = basis[i]

        if b >= q90:
            events.append(BasisEvent(idx=i, direction=-1))  # SHORT
        elif b <= q10:
            events.append(BasisEvent(idx=i, direction=+1))  # LONG

    return events


# ---------------------------------------------------------------------------
# Returns computation
# ---------------------------------------------------------------------------

def compute_returns(
    events: list[BasisEvent],
    opens: list[float],
    horizon: int,
    max_idx: int,
) -> tuple[list[float], int]:
    """
    entry = opens[idx+1], exit = opens[idx+1+H]
    Non-overlapping on idx values.
    """
    included: list[float] = []
    n_excluded = 0
    last_included_idx: int | None = None

    for ev in events:
        idx = ev.idx
        entry_i = idx + 1
        exit_i  = idx + 1 + horizon

        if exit_i > max_idx:
            n_excluded += 1
            continue

        if last_included_idx is not None and idx < last_included_idx + horizon + 1:
            n_excluded += 1
            continue

        entry_price = opens[entry_i]
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
    events: list[BasisEvent],
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

def print_results(results: list[dict], split: str, n_aligned: int) -> None:
    print(f"\n{'='*72}")
    print(f"HYP-H-001 Basis Extreme Reversal -- SPLIT: {split.upper()}")
    print(f"rolling_window={ROLLING_WINDOW}, percentiles=[{PERCENTILE_LOW},{PERCENTILE_HIGH}], "
          f"horizons={ALL_HORIZONS}, Holm-Bonferroni alpha=0.05")
    print(f"Aligned perp+spot candles (inner join): {n_aligned}")
    print(f"{'='*72}")
    print(f"NOTE: Event study only. Positive result != profitable strategy.\n")

    if results:
        first = results[0]
        print(f"Total basis extreme events: "
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
        print("PRIMARY DECISION: FAILS TO REJECT H_null -- no statistically significant basis edge")
    print("(This is a TRAIN result only. Must validate on VALIDATION before acting.)")

    print("\nLIMITATIONS:")
    print("  - Gross returns only: no fees (~10.5 bps/leg), no funding, no slippage")
    print("  - Spot data starts at 04:00 UTC; first ~4 perp candles have no inner-join match")
    print("  - p-values use normal approximation (valid n>=30; approximate for smaller n)")
    print("  - rolling_window=400 is pre-registered; changing it = new hypothesis")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="HYP-H-001 Basis Extreme Reversal Event Study")
    parser.add_argument("--split", choices=["train", "validation", "oos"], default="train")
    args = parser.parse_args()

    if args.split != "train":
        print(f"WARNING: Running on {args.split.upper()} requires separate authorization.")
        confirm = input("Type 'yes' to continue: ")
        if confirm.strip().lower() != "yes":
            print("Aborted.")
            sys.exit(0)

    print(f"Loading perp: {PERP_FILE}...")
    perp_all = load_candles(PERP_FILE, PERP_HASH)
    print(f"Total perp candles: {len(perp_all)}. Hash verified.")

    print(f"Loading spot: {SPOT_FILE}...")
    spot_all = load_candles(SPOT_FILE, SPOT_HASH)
    print(f"Total spot candles: {len(spot_all)}. Hash verified.")

    aligned_perp, basis = build_aligned_series(perp_all, spot_all, args.split)
    if not aligned_perp:
        print(f"ERROR: No aligned candles for split '{args.split}'.")
        sys.exit(1)
    print(f"Split '{args.split}': {len(aligned_perp)} aligned perp+spot candles "
          f"({aligned_perp[0]['open_time'][:10]} to {aligned_perp[-1]['open_time'][:10]})")

    events = find_events(aligned_perp, basis)
    opens  = [float(c["open"]) for c in aligned_perp]
    max_idx = len(opens) - 1

    results = run_event_study(events, opens, ALL_HORIZONS, max_idx)
    print_results(results, args.split, len(aligned_perp))


if __name__ == "__main__":
    main()
