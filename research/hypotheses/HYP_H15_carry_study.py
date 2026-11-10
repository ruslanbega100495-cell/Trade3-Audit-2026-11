"""
HYP-H15: Funding Rate Carry Study — BTCUSDT
Tests systematic SHORT on positive funding / LONG on negative funding.
DISTINCT from HYP-G-001: H15 measures CARRY (price + funding), not price reversal.
Pre-registered 2026-10-25.
"""
import json, math, sys
from pathlib import Path
from datetime import datetime, timezone

FUNDING_FILE = Path("research/datasets/raw/bybit/BTCUSDT/funding/2024-01-01_2026-09-30.json")
OHLCV_FILE = Path("research/datasets/raw/bybit/BTCUSDT/H4/2024-01-01_2026-09-30.json")
FUNDING_HASH = "5b8057d195a7c8a9"
OHLCV_HASH = "e182346101e28d26"

TRAIN_START = "2024-01-01"
TRAIN_END = "2025-04-01"

# Pre-registered thresholds
LONG_THRESHOLD = -0.00005   # -0.005% in decimal
SHORT_THRESHOLD = 0.00008   # +0.008% in decimal
ROLLING_N = 3               # avg of last 3 funding periods
HOLD_BARS = 2               # H4 bars to hold (= 8h)

# Costs (pre-registered)
TAKER_FEE = 0.00055  # 0.055% per leg
SLIPPAGE = 0.00050   # 0.05% per leg
ROUND_TRIP_COST = (TAKER_FEE + SLIPPAGE) * 2  # 0.21% total


def load_funding():
    d = json.load(open(FUNDING_FILE))
    if d.get("dataset_hash") != FUNDING_HASH:
        raise ValueError(f"Funding hash mismatch: got {d.get('dataset_hash')}")
    return sorted(d["records"], key=lambda r: r["timestamp_ms"])


def load_ohlcv():
    d = json.load(open(OHLCV_FILE))
    if d.get("dataset_hash") != OHLCV_HASH:
        raise ValueError(f"OHLCV hash mismatch: got {d.get('dataset_hash')}")
    return d["candles"]


def filter_train(records, key="timestamp_iso"):
    return [r for r in records if TRAIN_START <= r[key][:10] < TRAIN_END]


def filter_train_ohlcv(candles):
    return [c for c in candles if TRAIN_START <= c["open_time"][:10] < TRAIN_END]


def candle_open_ms(candle):
    dt = datetime.fromisoformat(candle["open_time"].replace("+00:00", ""))
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


def find_next_candle_idx(funding_ts_ms, candle_ms_list):
    """First candle index with open_time_ms > funding_ts_ms (NEXT after settlement)."""
    import bisect
    idx = bisect.bisect_right(candle_ms_list, funding_ts_ms)
    return idx  # returns N if not found


def run_carry_study(funding_records, candles_train):
    candle_ms = [candle_open_ms(c) for c in candles_train]
    opens = [float(c["open"]) for c in candles_train]
    n_candles = len(candles_train)

    trades = []

    # Process each funding settlement
    for i in range(ROLLING_N - 1, len(funding_records)):
        rec = funding_records[i]

        # Skip if outside TRAIN
        if not (TRAIN_START <= rec["timestamp_iso"][:10] < TRAIN_END):
            continue

        # Rolling avg of last ROLLING_N funding rates
        window = [funding_records[j]["funding_rate"] for j in range(i - ROLLING_N + 1, i + 1)]
        avg_f = sum(window) / len(window)

        # Signal
        if avg_f > SHORT_THRESHOLD:
            direction = -1  # SHORT
        elif avg_f < LONG_THRESHOLD:
            direction = +1  # LONG
        else:
            continue  # no position

        # Entry: next H4 candle after funding settlement
        funding_ts = rec["timestamp_ms"]
        entry_idx = find_next_candle_idx(funding_ts, candle_ms)
        if entry_idx >= n_candles:
            continue

        # Exit: HOLD_BARS later
        exit_idx = entry_idx + HOLD_BARS
        if exit_idx >= n_candles:
            continue

        entry_price = opens[entry_idx]
        exit_price = opens[exit_idx]

        # Price return (direction-adjusted)
        price_return = direction * (exit_price - entry_price) / entry_price

        # Funding earned during hold period
        # Find funding settlements between entry and exit
        entry_ms = candle_ms[entry_idx]
        exit_ms = candle_ms[exit_idx]
        funding_earned = 0.0
        for j in range(len(funding_records)):
            ft = funding_records[j]["timestamp_ms"]
            if entry_ms <= ft < exit_ms:
                # Funding sign logic:
                # funding_rate > 0 → longs pay shorts
                # SHORT (direction=-1): earns +funding_rate
                #   earned = direction × (-1) × funding_rate = -1 × -1 × fr = +fr ✓
                # LONG (direction=+1): pays +funding_rate
                #   earned = direction × (-1) × funding_rate = +1 × -1 × fr = -fr ✓
                funding_earned += direction * (-1) * funding_records[j]["funding_rate"]

        net_return = price_return + funding_earned - ROUND_TRIP_COST

        trades.append({
            "entry_time": candles_train[entry_idx]["open_time"],
            "direction": direction,
            "avg_funding_signal": avg_f,
            "price_return": price_return,
            "funding_earned": funding_earned,
            "net_return": net_return,
            "entry_price": entry_price,
            "exit_price": exit_price,
        })

    return trades


def compute_stats(trades):
    if not trades:
        return {}

    rets = [t["net_return"] for t in trades]
    n = len(rets)
    mean_r = sum(rets) / n
    std_r = math.sqrt(sum((r - mean_r)**2 for r in rets) / (n - 1)) if n > 1 else 0

    # Daily aggregated returns
    from collections import defaultdict
    daily = defaultdict(float)
    for t in trades:
        day = t["entry_time"][:10]
        daily[day] += t["net_return"]

    daily_vals = list(daily.values())
    n_days = len(daily_vals)
    daily_mean = sum(daily_vals) / n_days if n_days > 0 else 0
    daily_std = math.sqrt(sum((x - daily_mean)**2 for x in daily_vals) / (n_days - 1)) if n_days > 1 else 0
    sharpe = (daily_mean / daily_std * math.sqrt(252)) if daily_std > 0 else float("nan")

    # Max drawdown on cumulative returns
    cumulative = 0
    peak = 0
    max_dd = 0
    for r in rets:
        cumulative += r
        if cumulative > peak:
            peak = cumulative
        dd = peak - cumulative
        if dd > max_dd:
            max_dd = dd

    n_short = sum(1 for t in trades if t["direction"] == -1)
    n_long = sum(1 for t in trades if t["direction"] == +1)

    price_returns = [t["price_return"] for t in trades]
    funding_returns = [t["funding_earned"] for t in trades]

    return {
        "n_trades": n,
        "n_short": n_short,
        "n_long": n_long,
        "mean_net_return_pct": round(mean_r * 100, 4),
        "std_net_return_pct": round(std_r * 100, 4),
        "mean_price_return_pct": round(sum(price_returns) / n * 100, 4),
        "mean_funding_earned_pct": round(sum(funding_returns) / n * 100, 4),
        "mean_cost_pct": round(ROUND_TRIP_COST * 100, 4),
        "total_net_return_pct": round(sum(rets) * 100, 4),
        "sharpe_annualized": round(sharpe, 3) if not math.isnan(sharpe) else None,
        "max_drawdown_pct": round(max_dd * 100, 4),
        "win_rate": round(sum(1 for r in rets if r > 0) / n, 3),
    }


def main():
    funding_all = load_funding()
    ohlcv_all = load_ohlcv()

    funding_train = filter_train(funding_all, key="timestamp_iso")
    candles_train = filter_train_ohlcv(ohlcv_all)

    print(f"Funding records in TRAIN: {len(funding_train)}")
    print(f"OHLCV candles in TRAIN: {len(candles_train)}")
    print(f"Funding range: {funding_train[0]['timestamp_iso'][:10]} to {funding_train[-1]['timestamp_iso'][:10]}")

    trades = run_carry_study(funding_train, candles_train)
    stats = compute_stats(trades)

    print(f"\n{'='*60}")
    print("HYP-H15 Funding Carry Study — TRAIN")
    print(f"Thresholds: SHORT >{SHORT_THRESHOLD*100:.3f}%, LONG <{LONG_THRESHOLD*100:.3f}%")
    print(f"Rolling avg: {ROLLING_N} funding periods, hold: {HOLD_BARS} H4 bars")
    print(f"{'='*60}")

    if not stats:
        print("NO TRADES generated. Check thresholds.")
        return

    print(f"\nN trades: {stats['n_trades']} (SHORT={stats['n_short']}, LONG={stats['n_long']})")
    print(f"\nReturn decomposition (per trade):")
    print(f"  Price return:    {stats['mean_price_return_pct']:+.4f}%")
    print(f"  Funding earned:  {stats['mean_funding_earned_pct']:+.4f}%")
    print(f"  Round-trip cost: -{stats['mean_cost_pct']:.4f}%")
    print(f"  Net return:      {stats['mean_net_return_pct']:+.4f}%")
    print(f"\nRisk metrics:")
    print(f"  Sharpe (annualized): {stats['sharpe_annualized']}")
    print(f"  Max drawdown:   {stats['max_drawdown_pct']:.4f}%")
    print(f"  Win rate:       {stats['win_rate']:.3f}")
    print(f"  Total net PnL:  {stats['total_net_return_pct']:+.4f}%")

    # Decision
    print(f"\n{'='*60}")
    if stats['mean_net_return_pct'] > 0 and stats['n_trades'] >= 50 and (stats['sharpe_annualized'] or 0) > 0.3:
        print("PRELIMINARY DECISION: PROMISING — positive net return with carry")
    elif stats['mean_net_return_pct'] > 0:
        print("PRELIMINARY DECISION: WEAK POSITIVE — net positive but insufficient evidence")
    else:
        print("PRELIMINARY DECISION: FAILS TO SHOW CARRY ADVANTAGE")
    print("(TRAIN result only. VALIDATION requires separate authorization.)")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
