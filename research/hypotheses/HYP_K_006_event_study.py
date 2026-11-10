"""
HYP-K-006: Funding Rate Extreme + OI Contraction — BTCUSDT H4 Event Study

Pre-registered 2026-10-25. See research/registry/HYP-K-006.yaml for full spec.

Mechanism: Extreme high funding + falling OI = longs being liquidated/distributed.
Adds OI filter to G-001 (funding only, REJECTED) to test the real distribution phase.

Usage:
    python -m research.hypotheses.HYP_K_006_event_study --split train
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

FUNDING_FILE = Path(__file__).parent.parent / "datasets/raw/bybit/BTCUSDT/funding/2024-01-01_2026-09-30.json"
OI_FILE      = Path(__file__).parent.parent / "datasets/raw/bybit/BTCUSDT/H4/oi_2024-01-01_2026-09-30.json"
OHLCV_FILE   = Path(__file__).parent.parent / "datasets/raw/bybit/BTCUSDT/H4/2024-01-01_2026-09-30.json"

FUNDING_HASH = "5b8057d195a7c8a9"
OHLCV_HASH   = "e182346101e28d26"

ROLLING_WINDOW = 400
ALL_HORIZONS   = [4, 8, 16, 32]

SPLITS = {
    "train":      ("2024-01-01", "2025-04-01"),
    "validation": ("2025-04-01", "2025-10-01"),
    "oos":        ("2025-10-01", "2026-07-01"),
}


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def iso_to_ms(iso_str: str) -> int:
    """Convert ISO 8601 UTC string to ms epoch. Handles '+00:00' or no-tz."""
    s = iso_str
    if s.endswith("+00:00"):
        s = s[:-6]
    elif s.endswith("Z"):
        s = s[:-1]
    # Supports 'YYYY-MM-DD' and 'YYYY-MM-DDTHH:MM:SS'
    if len(s) == 10:
        s = s + "T00:00:00"
    dt = datetime(
        int(s[0:4]), int(s[5:7]), int(s[8:10]),
        int(s[11:13]), int(s[14:16]), int(s[17:19]),
        tzinfo=timezone.utc,
    )
    return int(dt.timestamp() * 1000)


def percentile(values: list[float], p: float) -> float:
    """p-th percentile (0-100) via linear interpolation. No scipy needed."""
    n = len(values)
    if n == 0:
        raise ValueError("Empty list")
    sv = sorted(values)
    idx = (p / 100.0) * (n - 1)
    lo = int(idx)
    hi = lo + 1
    if hi >= n:
        return sv[-1]
    return sv[lo] + (idx - lo) * (sv[hi] - sv[lo])


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_funding() -> list[dict]:
    with open(FUNDING_FILE, encoding="utf-8") as f:
        d = json.load(f)
    if d.get("dataset_hash") != FUNDING_HASH:
        raise ValueError(
            f"Funding hash mismatch: stored={d.get('dataset_hash')} expected={FUNDING_HASH}"
        )
    return d["records"]


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


def filter_ohlcv_split(candles: list[dict], split: str) -> list[dict]:
    start_ms = iso_to_ms(SPLITS[split][0])
    end_ms   = iso_to_ms(SPLITS[split][1])
    return [c for c in candles if start_ms <= c["ts_ms"] < end_ms]


# ---------------------------------------------------------------------------
# Signal detection
# ---------------------------------------------------------------------------

@dataclass
class FundOiEvent:
    funding_idx: int   # index in global funding list
    funding_ts_ms: int
    direction: int     # -1=SHORT, +1=LONG
    entry_idx: int     # index in TRAIN OHLCV array (entry at open[entry_idx])


def build_events(
    funding_all: list[dict],
    oi_all: list[dict],
    ohlcv_split: list[dict],
    split: str,
) -> list[FundOiEvent]:
    """
    Produce signal events for the given split.

    Lookahead checks:
    - funding_rate[t]: known at settlement time [OK]
    - OI[t]: last bar with ts_ms <= funding_ts [OK, prior data]
    - Rolling window: funding_rate[t-400:t], excludes t [OK]
    - Entry: first candle with open_time_ms >= funding_ts [OK, next or same bar after settlement]
    """
    start_ms = iso_to_ms(SPLITS[split][0])
    end_ms   = iso_to_ms(SPLITS[split][1])

    oi_ts   = [r["timestamp_ms"] for r in oi_all]
    oi_vals = [r["open_interest"] for r in oi_all]

    ohlcv_ts = [c["ts_ms"] for c in ohlcv_split]

    funding_rates = [r["funding_rate"] for r in funding_all]

    events: list[FundOiEvent] = []

    for j, fr in enumerate(funding_all):
        ft_ms = fr["timestamp_ms"]

        # Only signal events in the target split
        if not (start_ms <= ft_ms < end_ms):
            continue

        # Warmup: need 400 prior funding records
        if j < ROLLING_WINDOW:
            continue

        # OI alignment: last OI bar with ts <= funding_ts
        oi_idx = bisect.bisect_right(oi_ts, ft_ms) - 1
        if oi_idx < 4:
            continue  # need 4 prior OI bars for OI_delta

        oi_delta = oi_vals[oi_idx] - oi_vals[oi_idx - 4]

        # Rolling percentiles for funding
        window = funding_rates[j - ROLLING_WINDOW : j]
        q90 = percentile(window, 90)
        q10 = percentile(window, 10)

        fr_val = fr["funding_rate"]

        direction: int | None = None
        if fr_val >= q90 and oi_delta < 0:
            direction = -1  # SHORT: extreme positive funding + OI falling
        elif fr_val <= q10 and oi_delta < 0:
            direction = +1  # LONG: extreme negative funding + OI falling

        if direction is None:
            continue

        # Entry: first TRAIN candle with open_time_ms >= funding_ts
        entry_idx = bisect.bisect_left(ohlcv_ts, ft_ms)
        if entry_idx >= len(ohlcv_ts):
            continue  # no valid candle in split

        events.append(FundOiEvent(
            funding_idx=j,
            funding_ts_ms=ft_ms,
            direction=direction,
            entry_idx=entry_idx,
        ))

    return events


# ---------------------------------------------------------------------------
# Returns with non-overlapping window
# ---------------------------------------------------------------------------

def compute_returns(
    events: list[FundOiEvent],
    opens: list[float],
    horizon: int,
    max_idx: int,
) -> tuple[list[float], int]:
    """
    Direction-adjusted returns. Non-overlapping by entry candle index.
    exclude if exit_i > max_idx or entry overlaps prior window.
    """
    included: list[float] = []
    n_excluded = 0
    last_entry_idx: int | None = None

    for ev in sorted(events, key=lambda e: e.entry_idx):
        exit_i = ev.entry_idx + horizon

        if exit_i > max_idx:
            n_excluded += 1
            continue

        if last_entry_idx is not None and ev.entry_idx < last_entry_idx + horizon + 1:
            n_excluded += 1
            continue

        entry_price = opens[ev.entry_idx]
        exit_price  = opens[exit_i]
        raw_ret = (exit_price - entry_price) / entry_price
        included.append(ev.direction * raw_ret)
        last_entry_idx = ev.entry_idx

    return included, n_excluded


# ---------------------------------------------------------------------------
# Statistics (stdlib only — same as K-002)
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
    events: list[FundOiEvent],
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

def print_results(results: list[dict], split: str) -> None:
    n_short = results[0]["n_short"] if results else 0
    n_long  = results[0]["n_long"]  if results else 0
    n_total = n_short + n_long

    print(f"\n{'='*72}")
    print(f"HYP-K-006 Funding Extreme + OI Contraction — SPLIT: {split.upper()}")
    print(f"rolling_window={ROLLING_WINDOW}, horizons={ALL_HORIZONS}, Holm-Bonferroni alpha=0.05")
    print(f"{'='*72}")
    print(f"Signal events: SHORT={n_short}, LONG={n_long}, TOTAL={n_total}")
    print(f"(SHORT = extreme positive funding + OI falling; LONG = extreme negative funding + OI falling)\n")

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
    print("  - LONG branch (extreme negative funding + OI falling) has less direct mechanism")
    print("  - entry = first H4 open >= funding settlement time (0h, 8h, 16h UTC)")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="HYP-K-006 Event Study")
    parser.add_argument("--split", choices=["train", "validation", "oos"], default="train")
    args = parser.parse_args()

    if args.split != "train":
        print(f"WARNING: Running on {args.split.upper()} requires separate authorization.")
        confirm = input("Type 'yes' to continue: ")
        if confirm.strip().lower() != "yes":
            print("Aborted.")
            sys.exit(0)

    print(f"Loading funding ({FUNDING_FILE.name})...")
    funding_all = load_funding()
    print(f"  {len(funding_all)} records. Hash verified: {FUNDING_HASH}")

    print(f"Loading OI ({OI_FILE.name})...")
    oi_all = load_oi()
    print(f"  {len(oi_all)} records.")

    print(f"Loading OHLCV ({OHLCV_FILE.name})...")
    ohlcv_all = load_ohlcv()
    print(f"  {len(ohlcv_all)} candles. Hash verified: {OHLCV_HASH}")

    ohlcv_split = filter_ohlcv_split(ohlcv_all, args.split)
    print(f"Split '{args.split}': {len(ohlcv_split)} candles "
          f"({ohlcv_split[0]['open_time'][:10]} to {ohlcv_split[-1]['open_time'][:10]})")

    opens   = [float(c["open"]) for c in ohlcv_split]
    max_idx = len(opens) - 1

    print("Building signal events (funding extreme + OI contraction)...")
    events = build_events(funding_all, oi_all, ohlcv_split, args.split)
    n_short = sum(1 for e in events if e.direction == -1)
    n_long  = sum(1 for e in events if e.direction == +1)
    print(f"  Found {len(events)} events (SHORT={n_short}, LONG={n_long})")

    results = run_event_study(events, opens, ALL_HORIZONS, max_idx)
    print_results(results, args.split)


if __name__ == "__main__":
    main()
