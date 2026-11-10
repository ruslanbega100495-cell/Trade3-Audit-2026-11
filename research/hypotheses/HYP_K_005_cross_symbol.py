"""
HYP-K-005 Cross-Symbol Runner -- tests the same sweep+structure signal on ETH/SOL/BNB.
Spec: identical to HYP-K-005 (sweep_lookback=20, confirm_window=20).
Pre-registered 2026-10-25. See research/registry/HYP-K-005-ETH/SOL/BNB.yaml.

Usage:
    python -m research.hypotheses.HYP_K_005_cross_symbol
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

# Dataset hashes filled in after download
DATA_FILES = {
    "ETHUSDT": ("9e3920e4151c19d7",  str(Path(__file__).parent.parent / "datasets/raw/bybit/ETHUSDT/H4/2024-01-01_2026-09-30.json")),
    "SOLUSDT": ("2df9c98b6975a81d",  str(Path(__file__).parent.parent / "datasets/raw/bybit/SOLUSDT/H4/2024-01-01_2026-09-30.json")),
    "BNBUSDT": ("efc2e0f10bdf2495",  str(Path(__file__).parent.parent / "datasets/raw/bybit/BNBUSDT/H4/2024-01-01_2026-09-30.json")),
}

TRAIN_START    = "2024-01-01"
TRAIN_END      = "2025-04-01"
SWEEP_N        = 20
CONFIRM_WINDOW = 20
ALL_HORIZONS   = [4, 8, 16, 32]


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def load_candles(filepath: str, expected_hash: str) -> list[dict]:
    with open(filepath, encoding="utf-8") as f:
        d = json.load(f)
    if d.get("dataset_hash") != expected_hash:
        raise ValueError(
            f"Hash mismatch in {filepath}: expected {expected_hash}, got {d.get('dataset_hash')}"
        )
    return d["candles"]


def filter_train(candles: list[dict]) -> list[dict]:
    return [c for c in candles if TRAIN_START <= c["open_time"][:10] < TRAIN_END]


# ---------------------------------------------------------------------------
# Signal detection (same logic as HYP-K-005)
# ---------------------------------------------------------------------------

@dataclass
class StructureBreakEvent:
    idx: int        # lh+2 (confirmation bar); entry = opens[lh+3]
    direction: int  # -1 SHORT, +1 LONG


def find_events(candles: list[dict]) -> list[StructureBreakEvent]:
    """
    SHORT:
      Sweep bar s: high[s] > max(high[s-20:s]) AND close[s] < max(high[s-20:s])
      Find first lh in [s+1, s+20] where:
        high[lh] > high[lh-1] AND high[lh] > high[lh+1] AND high[lh] > high[lh+2]
        AND high[lh] < high[s]   (confirmed lower high)
      Event idx = lh+2, entry = opens[lh+3]

    LONG:
      Sweep bar s: low[s] < min(low[s-20:s]) AND close[s] > min(low[s-20:s])
      Find first hl in [s+1, s+20] where:
        low[hl] < low[hl-1] AND low[hl] < low[hl+1] AND low[hl] < low[hl+2]
        AND low[hl] > low[s]   (confirmed higher low)
      Event idx = hl+2, entry = opens[hl+3]
    """
    highs  = [float(c["high"])  for c in candles]
    lows   = [float(c["low"])   for c in candles]
    closes = [float(c["close"]) for c in candles]
    n = len(candles)

    events: list[StructureBreakEvent] = []

    for s in range(SWEEP_N, n):
        # SHORT: sweep of rolling 20-bar high
        level_high = max(highs[s - SWEEP_N: s])
        if highs[s] > level_high and closes[s] < level_high:
            for lh in range(s + 1, min(s + 1 + CONFIRM_WINDOW, n)):
                if lh - 1 < 0 or lh + 2 >= n:
                    continue
                if (highs[lh] > highs[lh - 1]
                        and highs[lh] > highs[lh + 1]
                        and highs[lh] > highs[lh + 2]
                        and highs[lh] < highs[s]):
                    conf_bar  = lh + 2
                    entry_bar = lh + 3
                    if entry_bar < n:
                        events.append(StructureBreakEvent(idx=conf_bar, direction=-1))
                    break

        # LONG: sweep of rolling 20-bar low
        level_low = min(lows[s - SWEEP_N: s])
        if lows[s] < level_low and closes[s] > level_low:
            for lh in range(s + 1, min(s + 1 + CONFIRM_WINDOW, n)):
                if lh - 1 < 0 or lh + 2 >= n:
                    continue
                if (lows[lh] < lows[lh - 1]
                        and lows[lh] < lows[lh + 1]
                        and lows[lh] < lows[lh + 2]
                        and lows[lh] > lows[s]):
                    conf_bar  = lh + 2
                    entry_bar = lh + 3
                    if entry_bar < n:
                        events.append(StructureBreakEvent(idx=conf_bar, direction=+1))
                    break

    events.sort(key=lambda e: e.idx)
    return events


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
# Returns
# ---------------------------------------------------------------------------

def compute_returns(
    events: list[StructureBreakEvent],
    opens: list[float],
    horizon: int,
    max_idx: int,
) -> tuple[list[float], int]:
    included: list[float] = []
    n_excluded = 0
    last_included_idx: int | None = None

    for ev in events:
        idx   = ev.idx
        exit_i = idx + 1 + horizon

        if exit_i > max_idx:
            n_excluded += 1
            continue

        if last_included_idx is not None and idx < last_included_idx + horizon + 1:
            n_excluded += 1
            continue

        entry_price  = opens[idx + 1]
        exit_price   = opens[exit_i]
        raw_return   = (exit_price - entry_price) / entry_price
        direction_adj = ev.direction * raw_return
        included.append(direction_adj)
        last_included_idx = idx

    return included, n_excluded


# ---------------------------------------------------------------------------
# Per-symbol runner
# ---------------------------------------------------------------------------

def run_symbol(symbol: str, expected_hash: str, filepath: str) -> dict:
    print(f"\n--- {symbol} ---")
    candles_all   = load_candles(filepath, expected_hash)
    candles_train = filter_train(candles_all)
    print(f"Train candles: {len(candles_train)} "
          f"({candles_train[0]['open_time'][:10]} to {candles_train[-1]['open_time'][:10]})")

    events  = find_events(candles_train)
    opens   = [float(c["open"]) for c in candles_train]
    max_idx = len(opens) - 1

    n_total = len(events)
    n_short = sum(1 for e in events if e.direction == -1)
    n_long  = sum(1 for e in events if e.direction == +1)
    print(f"Events: SHORT={n_short}, LONG={n_long}, TOTAL={n_total}")

    rows: list[dict] = []
    p_values: list[float] = []

    for H in ALL_HORIZONS:
        ret, n_excl = compute_returns(events, opens, H, max_idx)
        n = len(ret)
        if n < 5:
            t, p = float("nan"), float("nan")
        else:
            t, p = t_stat(ret)
        rows.append({
            "horizon": H,
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
    for i, r in enumerate(rows):
        r["holm_reject"] = rejects[i]

    print(f"\n{'H':>4} {'N_incl':>7} {'N_excl':>7} {'mean%':>8} {'std%':>7} "
          f"{'t':>7} {'p':>9} {'Holm':>8}")
    print("-" * 65)
    for r in rows:
        mean_str = f"{r['mean_dir_return_pct']:8.4f}" if r["mean_dir_return_pct"] is not None else "     n/a"
        std_str  = f"{r['std_pct']:7.4f}" if r["std_pct"] is not None else "    n/a"
        t_str    = f"{r['t_stat']:7.3f}" if r["t_stat"] is not None else "    n/a"
        p_str    = f"{r['p_value']:9.6f}" if r["p_value"] is not None else "      n/a"
        holm_str = "REJECT" if r["holm_reject"] else "keep  "
        print(f"{r['horizon']:>4} {r['n_included']:>7} {r['n_excluded']:>7} "
              f"{mean_str} {std_str} {t_str} {p_str} {holm_str}")

    any_reject = any(r["holm_reject"] for r in rows if r["holm_reject"] is not None)
    all_insuf  = all(r["p_value"] is None for r in rows)
    if all_insuf:
        decision = "INSUFFICIENT DATA"
    elif any_reject:
        decision = "PROMISING"
    else:
        decision = "FAILS TO REJECT"

    print(f"\n{symbol} PRIMARY DECISION: {decision}")
    return {
        "symbol": symbol,
        "n_events_total": n_total,
        "n_short": n_short,
        "n_long": n_long,
        "rows": rows,
        "decision": decision,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"{'='*72}")
    print("HYP-K-005 Cross-Symbol Runner — ETHUSDT / SOLUSDT / BNBUSDT")
    print(f"sweep_lookback={SWEEP_N}, confirm_window={CONFIRM_WINDOW}, "
          f"horizons={ALL_HORIZONS}, Holm-Bonferroni alpha=0.05")
    print(f"TRAIN SPLIT: {TRAIN_START} to {TRAIN_END}")
    print(f"BTC context (from HYP-K-005 TRAIN): H32 t=2.145, p=0.032, n=54 "
          f"-- NOT confirmed by Holm")
    print(f"{'='*72}")

    all_results = {}
    for symbol, (expected_hash, filepath) in DATA_FILES.items():
        result = run_symbol(symbol, expected_hash, filepath)
        all_results[symbol] = result

    print(f"\n{'='*72}")
    print("CROSS-SYMBOL SUMMARY")
    print(f"{'='*72}")
    print(f"{'Symbol':<10} {'N':>5} {'H4-t':>7} {'H8-t':>7} {'H16-t':>7} {'H32-t':>7}  Decision")
    print("-" * 72)
    for sym, res in all_results.items():
        rows = res["rows"]
        t_vals = [r["t_stat"] for r in rows]
        t_strs = [f"{t:7.3f}" if t is not None else "    n/a" for t in t_vals]
        print(f"{sym:<10} {res['n_events_total']:>5} {'  '.join(t_strs)}  {res['decision']}")

    # Transferability note
    promising_count = sum(1 for r in all_results.values() if r["decision"] == "PROMISING")
    print(f"\nTransferability: {promising_count}/3 symbols show Holm-confirmed edge "
          f"on at least one horizon.")
    if promising_count >= 2:
        print("NOTE: >= 2 symbols PROMISING — cross-symbol consistency is interesting. "
              "But TRAIN result only; validate on VALIDATION before drawing conclusions.")
    else:
        print("NOTE: < 2 symbols PROMISING — BTC H32 signal does not appear to transfer "
              "robustly across symbols in TRAIN.")

    print("\nLIMITATIONS:")
    print("  - Gross returns only: no fees (~10.5 bps/leg), no funding, no slippage")
    print("  - TRAIN period only; no OOS or HOLDOUT run")
    print("  - open[lh+3] entry assumes instant fill at open price")
    print("  - p-values use normal approximation")


if __name__ == "__main__":
    main()
