"""
HYP-H16 VALIDATION Research Run — frozen config, BTCUSDT H4.

Applies the frozen HYP-H16 winner from TRAIN (N=12, vol-scaled,
TARGET_VOL=0.20, LEVERAGE_CAP=2.0, VOL_WINDOW=20, MIN_VOL=0.05) to the
VALIDATION split [2025-04-01, 2025-10-01) allocated by DECISION D-001.
This is NOT holdout. No parameter tuning. Exploratory N=24 diagnostic
is reported separately and is NOT used for any selection.

Execution model — identical to research/hypotheses/HYP_H16_tsmom_study.py:
  - signal on CLOSE of bar t (sign of N-bar return + vol-scaling from the
    last VOL_WINDOW closes, all <= t — no look-ahead);
  - entry at OPEN of bar t+1, exit at OPEN of bar t+1+N (non-overlapping);
  - net_return = position * price_return - |position| * (fee+slippage) * 2.
Costs (frozen): TAKER_FEE=0.00055, SLIPPAGE=0.00050 per leg.
Funding NOT modeled (same as TRAIN — documented limitation).
Volatility warmup: bars of 2025-03 (past data only) are used so the
VOL_WINDOW=20 realized-vol is defined at the start of validation.

RESEARCH RULES:
- VALIDATION split only. OOS/HOLDOUT not loaded for evaluation.
- Parameters frozen. No tuning on validation.
- TRADING_DISABLED. No live orders, no API keys.

Usage:
    cd C:/Users/rusla/Trade/Trade3
    .venv/Scripts/python.exe -X utf8 scripts/run_hyp_h16_validation.py
"""
import json
import math
import sys
from pathlib import Path

from scipy import stats

ROOT = Path(__file__).parent.parent
DATA_FILE = ROOT / "research/datasets/raw/bybit/BTCUSDT/H4/2024-01-01_2026-09-30.json"
OUT_DIR = ROOT / "research/multi_exchange/BACKTESTS"
OUT_JSON = OUT_DIR / "HYP-H16_validation_output.json"

EXPECTED_HASH = "e182346101e28d26"
VALIDATION_START = "2025-04-01"
VALIDATION_END = "2025-10-01"
WARMUP_START = "2025-03-01"  # past-data warmup for the vol window only

# Frozen parameters (TRAIN winner, HYP-H16.yaml decision line)
N_FROZEN = 12
TAKER_FEE = 0.00055
SLIPPAGE = 0.00050
TARGET_VOL = 0.20
LEVERAGE_CAP = 2.0
VOL_WINDOW = 20
MIN_VOL = 0.05


def load_candles():
    d = json.load(open(DATA_FILE))
    if d.get("dataset_hash") != EXPECTED_HASH:
        raise ValueError(f"Hash mismatch: got {d.get('dataset_hash')}")
    # Warmup (2025-03) + validation bars. Nothing from >= VALIDATION_END.
    return [c for c in d["candles"]
            if WARMUP_START <= c["open_time"][:10] < VALIDATION_END]


def compute_signal(closes, t, N):
    """Identical to TRAIN study. Signal uses data up to and incl. close[t]."""
    if t < N + VOL_WINDOW:
        return None, None
    ret_N = closes[t] / closes[t - N] - 1
    direction = 1 if ret_N > 0 else -1
    log_rets = [math.log(closes[t - i] / closes[t - i - 1]) for i in range(VOL_WINDOW)]
    mean_lr = sum(log_rets) / len(log_rets)
    var_lr = sum((r - mean_lr) ** 2 for r in log_rets) / (len(log_rets) - 1)
    realized_vol = math.sqrt(var_lr) * math.sqrt(252 * 6)
    if realized_vol < MIN_VOL:
        return None, None
    position = direction * (TARGET_VOL / realized_vol)
    position = max(-LEVERAGE_CAP, min(LEVERAGE_CAP, position))
    return direction, position


def run_tsmom(candles, N_formation, cost_mult=1.0):
    """Same execution model as TRAIN. cost_mult=2.0 = 2x cost stress."""
    closes = [float(c["close"]) for c in candles]
    opens = [float(c["open"]) for c in candles]
    n = len(candles)

    # First signal bar inside the validation window. Non-overlapping cadence
    # t = t0 + k*N mirrors the TRAIN loop (t = N+VOL_WINDOW + k*N there).
    t0 = next(i for i, c in enumerate(candles)
              if c["open_time"][:10] >= VALIDATION_START)

    rt_cost = (TAKER_FEE + SLIPPAGE) * cost_mult
    trades = []
    t = t0
    while t < n - N_formation - 1:
        direction, position = compute_signal(closes, t, N_formation)
        entry_idx = t + 1
        exit_idx = t + 1 + N_formation
        if exit_idx >= n:
            break
        if direction is not None:
            entry_price = opens[entry_idx]
            exit_price = opens[exit_idx]
            price_return = (exit_price - entry_price) / entry_price
            net_return = position * price_return - abs(position) * rt_cost * 2
            trades.append({
                "signal_time": candles[t]["open_time"],
                "entry_time": candles[entry_idx]["open_time"],
                "exit_time": candles[exit_idx]["open_time"],
                "direction": direction,
                "position": round(position, 4),
                "price_return": round(price_return, 6),
                "net_return": round(net_return, 6),
            })
        t += N_formation
    return trades


def summarize(trades, label):
    from collections import defaultdict
    if not trades:
        print(f"{label}: NO TRADES")
        return {"label": label, "n_trades": 0}

    rets = [t["net_return"] for t in trades]
    n = len(rets)
    mean_r = sum(rets) / n
    std_r = math.sqrt(sum((r - mean_r) ** 2 for r in rets) / max(1, n - 1))

    daily = defaultdict(float)
    for t in trades:
        daily[t["entry_time"][:10]] += t["net_return"]
    dv = list(daily.values())
    daily_mean = sum(dv) / len(dv)
    daily_std = math.sqrt(sum((x - daily_mean) ** 2 for x in dv) / max(1, len(dv) - 1))
    sharpe = (daily_mean / daily_std * math.sqrt(252)) if daily_std > 0 else float("nan")

    cum = peak = mdd = 0.0
    for r in rets:
        cum += r
        peak = max(peak, cum)
        mdd = max(mdd, peak - cum)

    gross_profit = sum(r for r in rets if r > 0)
    gross_loss = -sum(r for r in rets if r < 0)
    pf = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

    # 95% CI on mean net return, t-distribution (df = n-1)
    tcrit = stats.t.ppf(0.975, n - 1)
    ci_half = tcrit * std_r / math.sqrt(n) if n > 1 else float("nan")

    n_long = sum(1 for t in trades if t["direction"] > 0)
    win_rate = sum(1 for r in rets if r > 0) / n

    print(f"\n{label} (n={n}, LONG={n_long}, SHORT={n - n_long})")
    print(f"  Period:                {trades[0]['entry_time'][:10]} -> {trades[-1]['exit_time'][:10]}")
    print(f"  Mean net return/trade: {mean_r * 100:+.4f}%")
    print(f"  Std:                   {std_r * 100:.4f}%")
    print(f"  95% CI (t, df={n - 1}):    [{(mean_r - ci_half) * 100:+.4f}%, {(mean_r + ci_half) * 100:+.4f}%]")
    sharpe_str = f"{sharpe:.3f}" if not math.isnan(sharpe) else "nan"
    print(f"  Sharpe (annualized):   {sharpe_str}")
    print(f"  Max drawdown:          {mdd * 100:.4f}%")
    print(f"  Total PnL (sum):       {sum(rets) * 100:+.4f}%")
    print(f"  Profit factor (net):   {pf:.3f}")
    print(f"  Win rate:              {win_rate:.3f}")

    return {
        "label": label,
        "n_trades": n,
        "n_long": n_long,
        "n_short": n - n_long,
        "mean_net_return_pct": round(mean_r * 100, 4),
        "std_pct": round(std_r * 100, 4),
        "ci95_t_dist": [round((mean_r - ci_half) * 100, 4), round((mean_r + ci_half) * 100, 4)],
        "sharpe_annualized": round(sharpe, 3) if not math.isnan(sharpe) else None,
        "max_drawdown_pct": round(mdd * 100, 4),
        "total_pnl_pct": round(sum(rets) * 100, 4),
        "profit_factor_net": round(pf, 3),
        "win_rate": round(win_rate, 3),
        "first_entry": trades[0]["entry_time"],
        "last_exit": trades[-1]["exit_time"],
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    candles = load_candles()
    n_val = sum(1 for c in candles if c["open_time"][:10] >= VALIDATION_START)
    print("=" * 70)
    print("HYP-H16 VALIDATION — frozen config (DECISION D-001 period allocation)")
    print("=" * 70)
    print("RESEARCH ONLY. TRADING_DISABLED. No live orders, no API keys.")
    print(f"Dataset hash: {EXPECTED_HASH} OK")
    print(f"Warmup bars (2025-03, past data only): {len(candles) - n_val}")
    print(f"Validation bars [{VALIDATION_START}, {VALIDATION_END}): {n_val}")
    print(f"Frozen: N={N_FROZEN}, vol-scaled, TARGET_VOL={TARGET_VOL}, "
          f"LEVERAGE_CAP={LEVERAGE_CAP}, VOL_WINDOW={VOL_WINDOW}, MIN_VOL={MIN_VOL}")
    print(f"Costs: taker={TAKER_FEE} + slippage={SLIPPAGE} per leg (round-trip x2)")
    print("Funding NOT modeled (identical to TRAIN cost model).")

    results = {}

    # Primary: frozen config, base costs
    t12 = run_tsmom(candles, N_FROZEN)
    results["N12_frozen_base"] = summarize(t12, "N=12, VOL-SCALED, base costs (FROZEN CONFIG)")

    # Cost stress: 2x fees+slippage (protocol requirement)
    t12_2x = run_tsmom(candles, N_FROZEN, cost_mult=2.0)
    results["N12_frozen_cost2x"] = summarize(t12_2x, "N=12, VOL-SCALED, 2x costs (stress)")

    # Exploratory diagnostic only (NOT for selection)
    t24 = run_tsmom(candles, 24)
    results["N24_exploratory"] = summarize(t24, "N=24, VOL-SCALED, base costs (EXPLORATORY diagnostic)")

    # TRAIN reference (from HYP-H16.yaml, not re-run)
    train_ref = {
        "N12_vol_scaled": {"n_trades": 225, "mean_net_return_pct": 0.2246,
                           "sharpe_annualized": 1.577, "max_drawdown_pct": 15.9131,
                           "total_pnl_pct": 50.5286, "win_rate": 0.533},
    }
    print("\n" + "=" * 70)
    print("TRAIN reference (from registry HYP-H16.yaml, 2024-01-01 -> 2025-04-01):")
    print(json.dumps(train_ref, indent=2))

    print("\n" + "=" * 70)
    print("VALIDATION EDGE CHECK (docs/VALIDATION_PROTOCOL.md):")
    r = results["N12_frozen_base"]
    s = results["N12_frozen_cost2x"]
    if r["n_trades"] > 0 and s["n_trades"] > 0:
        checks = {
            "expectancy>0": r["mean_net_return_pct"] > 0,
            "95% CI lower > 0": r["ci95_t_dist"][0] > 0,
            "2x costs expectancy > 0": s["mean_net_return_pct"] > 0,
            "2x costs CI lower > 0": s["ci95_t_dist"][0] > 0,
        }
        for k, v in checks.items():
            print(f"  {k:28s}: {'PASS' if v else 'FAIL'}")
        verdict = "PASS_VALIDATION" if all(checks.values()) else "FAIL_VALIDATION"
        print(f"\n  VERDICT: {verdict}")
    print("=" * 70)

    with open(OUT_JSON, "w") as f:
        json.dump({"config": {
            "N": N_FROZEN, "target_vol": TARGET_VOL, "leverage_cap": LEVERAGE_CAP,
            "vol_window": VOL_WINDOW, "min_vol": MIN_VOL,
            "taker_fee": TAKER_FEE, "slippage": SLIPPAGE,
            "validation_start": VALIDATION_START, "validation_end": VALIDATION_END,
            "warmup_start": WARMUP_START, "dataset_hash": EXPECTED_HASH,
        }, "results": results, "train_reference": train_ref},
            f, indent=2)
    print(f"\nRaw output written: {OUT_JSON}")
    print("\nNEXT STEPS:")
    print("  1. VALIDATION PASS != edge proven. Next: walk-forward, then prospective holdout only.")
    print("  2. Do NOT modify parameters based on this result.")
    print("  3. Period 2025-04->2025-10 becomes USED after review (PERIOD_MAP).")


if __name__ == "__main__":
    main()
