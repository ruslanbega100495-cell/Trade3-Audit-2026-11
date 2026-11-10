"""
HYP-H16: Vol-Normalized Time-Series Momentum — BTCUSDT H4
Pre-registered 2026-10-25.
"""
import json, math, sys
from pathlib import Path

DATA_FILE = Path("research/datasets/raw/bybit/BTCUSDT/H4/2024-01-01_2026-09-30.json")
EXPECTED_HASH = "e182346101e28d26"
TRAIN_START = "2024-01-01"
TRAIN_END = "2025-04-01"

# Pre-registered parameters
TAKER_FEE = 0.00055
SLIPPAGE = 0.00050
TARGET_VOL = 0.20
LEVERAGE_CAP = 2.0
VOL_WINDOW = 20
MIN_VOL = 0.05  # safety floor: no signal at anomalously low vol


def load_candles():
    d = json.load(open(DATA_FILE))
    if d.get("dataset_hash") != EXPECTED_HASH:
        raise ValueError(f"Hash mismatch: got {d.get('dataset_hash')}")
    candles = [c for c in d["candles"] if TRAIN_START <= c["open_time"][:10] < TRAIN_END]
    return candles


def compute_signal(closes, t, N):
    if t < N + VOL_WINDOW:
        return None, None

    # Direction: sign of N-bar return
    ret_N = closes[t] / closes[t - N] - 1
    direction = 1 if ret_N > 0 else -1

    # Realized vol: annualized std of log returns over last VOL_WINDOW bars
    log_rets = [math.log(closes[t - i] / closes[t - i - 1]) for i in range(VOL_WINDOW)]
    mean_lr = sum(log_rets) / len(log_rets)
    var_lr = sum((r - mean_lr)**2 for r in log_rets) / (len(log_rets) - 1)
    realized_vol = math.sqrt(var_lr) * math.sqrt(252 * 6)  # annualize: 252 days × 6 H4 bars/day

    if realized_vol < MIN_VOL:
        return None, None

    position = direction * (TARGET_VOL / realized_vol)
    position = max(-LEVERAGE_CAP, min(LEVERAGE_CAP, position))

    return direction, position


def run_tsmom(candles, N_formation, use_vol_scaling=True):
    closes = [float(c["close"]) for c in candles]
    opens = [float(c["open"]) for c in candles]
    n = len(candles)

    trades = []
    t = N_formation + VOL_WINDOW

    while t < n - N_formation - 1:
        direction, position = compute_signal(closes, t, N_formation)
        if direction is None:
            t += 1
            continue

        if not use_vol_scaling:
            position = float(direction)  # baseline: fixed ±1

        entry_idx = t + 1
        exit_idx = t + 1 + N_formation

        if exit_idx >= n:
            break

        entry_price = opens[entry_idx]
        exit_price = opens[exit_idx]

        price_return = (exit_price - entry_price) / entry_price
        net_return = position * price_return - abs(position) * (TAKER_FEE + SLIPPAGE) * 2

        trades.append({
            "t": t,
            "time": candles[t]["open_time"],
            "direction": direction,
            "position": position,
            "price_return": price_return,
            "net_return": net_return,
        })

        t += N_formation  # non-overlapping: advance by N

    return trades


def stats(trades, label):
    if not trades:
        print(f"{label}: NO TRADES")
        return {}

    rets = [t["net_return"] for t in trades]
    n = len(rets)
    mean_r = sum(rets) / n
    std_r = math.sqrt(sum((r - mean_r)**2 for r in rets) / max(1, n - 1))

    # Daily aggregated
    from collections import defaultdict
    daily = defaultdict(float)
    for t in trades:
        daily[t["time"][:10]] += t["net_return"]
    dv = list(daily.values())
    daily_mean = sum(dv) / len(dv)
    daily_std = math.sqrt(sum((x - daily_mean)**2 for x in dv) / max(1, len(dv) - 1))
    sharpe = (daily_mean / daily_std * math.sqrt(252)) if daily_std > 0 else float("nan")

    # Max drawdown
    cum = 0; peak = 0; mdd = 0
    for r in rets:
        cum += r
        peak = max(peak, cum)
        mdd = max(mdd, peak - cum)

    n_long = sum(1 for t in trades if t["direction"] > 0)

    print(f"\n{label} (N={n}, LONG={n_long}, SHORT={n - n_long})")
    print(f"  Mean net return/trade: {mean_r*100:+.4f}%")
    print(f"  Std:                   {std_r*100:.4f}%")
    sharpe_str = f"{sharpe:.3f}" if not math.isnan(sharpe) else "nan"
    print(f"  Sharpe (annualized):   {sharpe_str}")
    print(f"  Max drawdown:          {mdd*100:.4f}%")
    print(f"  Total PnL:             {sum(rets)*100:+.4f}%")
    print(f"  Win rate:              {sum(1 for r in rets if r > 0)/n:.3f}")

    if mean_r > 0 and (not math.isnan(sharpe)) and sharpe > 0.3 and n >= 30:
        print(f"  --> PROMISING")
    elif mean_r > 0:
        print(f"  --> WEAK POSITIVE (n={n}, sharpe={sharpe_str})")
    else:
        print(f"  --> NEGATIVE")

    return {
        "n_trades": n,
        "mean_net_return_pct": round(mean_r * 100, 4),
        "sharpe_annualized": round(sharpe, 3) if not math.isnan(sharpe) else None,
        "max_drawdown_pct": round(mdd * 100, 4),
        "win_rate": round(sum(1 for r in rets if r > 0) / n, 3),
    }


def main():
    candles = load_candles()
    print(f"TRAIN candles: {len(candles)} ({candles[0]['open_time'][:10]} to {candles[-1]['open_time'][:10]})")

    print(f"\n{'='*60}")
    print("HYP-H16: Vol-Normalized TSMOM — TRAIN RESULTS")
    print(f"{'='*60}")

    # Primary: N=24 (4-day), vol-scaled
    t24_vol = run_tsmom(candles, 24, use_vol_scaling=True)
    stats(t24_vol, "N=24 (4d), VOL-SCALED")

    # Baseline: N=24, no vol scaling
    t24_base = run_tsmom(candles, 24, use_vol_scaling=False)
    stats(t24_base, "N=24 (4d), BASELINE (no vol-scaling)")

    # Secondary: N=12 (2-day), vol-scaled (pre-registered)
    t12_vol = run_tsmom(candles, 12, use_vol_scaling=True)
    stats(t12_vol, "N=12 (2d), VOL-SCALED")

    print(f"\n{'='*60}")
    print("COST NOTE: taker_fee=0.055%/leg + slippage=0.05%/leg = 0.21% round-trip")
    print("Funding NOT included (long periods may have additional carry drain)")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
