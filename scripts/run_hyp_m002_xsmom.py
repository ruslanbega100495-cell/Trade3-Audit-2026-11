"""HYP-M-002: Cross-Sectional Momentum on 25 Bybit USDT perps (H4), TRAIN 2022-11-01..2025-04-01.

Dollar-neutral long top-k / short bottom-k by L-bar formation return,
rebalance every H bars. Costs: taker 0.00055 + slippage 0.00050 per side
(full turnover per rebalance). Funding: actual Bybit history, as-of join,
longs pay positive rate / shorts receive it (verified convention).

Look-ahead safety: signal from close of bar t -> positions on bars t+1..t+H.
All joins use only past data. Synchronized close matrix = inner join of bars
present in ALL symbols.
"""

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "research" / "datasets" / "raw" / "bybit"
REPORT_DIR = ROOT / "research" / "multi_exchange" / "BACKTESTS"

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
    "ADAUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT", "LTCUSDT", "BCHUSDT",
    "NEARUSDT", "UNIUSDT", "TRXUSDT", "XLMUSDT", "XMRUSDT", "AAVEUSDT",
    "CRVUSDT", "OPUSDT", "APTUSDT", "INJUSDT", "HBARUSDT", "STXUSDT",
    "ZECUSDT",
]

TAKER = 0.00055
SLIPPAGE = 0.00050
COST_PER_SIDE = TAKER + SLIPPAGE  # per unit notional
BARS_PER_DAY = 6
DAYS_PER_YEAR = 365

GRID_L = [24, 48, 96]
GRID_H = [4, 12]
GRID_K = [3, 5]

RNG = np.random.default_rng(42)


def load_close_matrix():
    """Inner join of H4 closes across all symbols (look-ahead-safe sync)."""
    frames = {}
    for sym in SYMBOLS:
        p = DATA / sym / "H4" / "2022-11-01_2025-04-01.json"
        d = json.loads(p.read_text())
        candles = d["candles"]
        idx = pd.to_datetime([c["open_time"] for c in candles])
        s = pd.Series(np.array([float(c["close"]) for c in candles]), index=idx)
        s = s[~s.index.duplicated(keep="last")]
        frames[sym] = s
    df = pd.DataFrame(frames).sort_index()
    df = df.dropna()  # only bars present in ALL symbols
    return df


def load_funding():
    """symbol -> Series(funding_rate) indexed by event timestamp."""
    out = {}
    for sym in SYMBOLS:
        p = DATA / sym / "funding" / "2022-11-01_2025-04-01.json"
        d = json.loads(p.read_text())
        idx = pd.to_datetime([r["timestamp_iso"] for r in d["records"]])
        vals = np.array([r["funding_rate"] for r in d["records"]], dtype="float64")
        out[sym] = pd.Series(vals, index=idx).sort_index()
    return out


def run_trial(closes, funding, L, H, k):
    """One (L, H, k) trial. Returns dict of results.

    Portfolio: gross=1, long top-k w=1/k each (leg=0.5), short bottom-k.
    Period p: signal at bar t, held bars t+1..t+H (close-to-close returns).
    Costs: full turnover (close + open) per rebalance = 2 * COST_PER_SIDE.
    Funding: bar open_time at 00/08/16 UTC -> held position pays/receives.
    """
    n_sym = len(closes.columns)
    rets = closes.pct_change()  # bar t-1 -> t close-to-close
    mom = closes / closes.shift(L) - 1.0

    # funding lookup: rate effective at event time e applies to a position
    # held at e. As-of: use funding record at the bar's open_time if present
    # (events are exactly on H4 grid 00/08/16).
    fund_at = {}
    for sym in closes.columns:
        s = funding[sym]
        fund_at[sym] = s.reindex(closes.index).ffill()

    timestamps = closes.index
    first_t = L  # first bar with momentum
    periods = []  # per-period detail
    t = first_t
    while t + H < len(closes):
        sig = mom.iloc[t]
        ranked = sig.dropna().sort_values()
        if len(ranked) < n_sym:  # require full cross-section
            t += H
            continue
        shorts = ranked.index[:k]
        longs = ranked.index[-k:]

        w = pd.Series(0.0, index=closes.columns)
        w[longs] = 1.0 / (2.0 * k)
        w[shorts] = -1.0 / (2.0 * k)

        gross_price_pnl = 0.0
        gross_fund_pnl = 0.0
        per_sym_pnl = pd.Series(0.0, index=closes.columns)
        held_bars = 0
        for h in range(1, H + 1):
            bar_ret = rets.iloc[t + h]
            gross_price_pnl += float((w * bar_ret).sum())
            for sym in longs.union(shorts):
                per_sym_pnl[sym] += w[sym] * bar_ret[sym]
            held_bars += 1
            # funding at bar open (00/08/16 UTC)
            ts = timestamps[t + h]
            if ts.hour in (0, 8, 16):
                for sym in longs.union(shorts):
                    fr = fund_at[sym].iloc[t + h]
                    if np.isnan(fr):
                        continue
                    # long pays fr, short receives fr (per unit notional)
                    fp = -w[sym] * fr
                    gross_fund_pnl += fp
                    per_sym_pnl[sym] += fp

        costs = 2.0 * COST_PER_SIDE  # full close + open turnover, gross=1
        net = gross_price_pnl + gross_fund_pnl - costs

        periods.append({
            "t": timestamps[t],
            "period_end": timestamps[t + H],
            "price_pnl": gross_price_pnl,
            "funding_pnl": gross_fund_pnl,
            "costs": costs,
            "net": net,
            "per_sym": per_sym_pnl,
        })
        t += H

    if len(periods) < 30:
        return None

    df = pd.DataFrame([{k: v for k, v in p.items() if k != "per_sym"} for p in periods])
    per_sym = pd.DataFrame([p["per_sym"] for p in periods]).fillna(0.0)
    n = len(df)
    periods_per_year = (BARS_PER_DAY * DAYS_PER_YEAR) / H
    mean_net = df["net"].mean()
    std_net = df["net"].std(ddof=1)
    sharpe = (mean_net / std_net * math.sqrt(periods_per_year)) if std_net > 0 else 0.0
    total_net = df["net"].sum()

    # Max drawdown on cumulative per-period return
    cum = df["net"].cumsum()
    dd = (cum - cum.cummax())
    max_dd = -dd.min() if len(dd) else 0.0

    gains = df.loc[df["net"] > 0, "net"].sum()
    losses = -df.loc[df["net"] < 0, "net"].sum()
    pf = (gains / losses) if losses > 0 else float("inf")

    hit = (df["net"] > 0).mean()

    # --- block bootstrap CI of mean net per-period return ---
    # circular block bootstrap, block length ~ sqrt(n) periods
    blk = max(2, int(math.sqrt(n)))
    n_boot = 10000
    boot_means = np.empty(n_boot)
    x = df["net"].to_numpy()
    for b in range(n_boot):
        starts = RNG.integers(0, n, size=int(np.ceil(n / blk)) + 1)
        samp = np.concatenate([x[s:min(s + blk, n)] if s + blk <= n
                               else np.concatenate([x[s:], x[: (s + blk) % n]])
                               for s in starts])[:n]
        boot_means[b] = samp.mean()
    ci_lo, ci_hi = np.percentile(boot_means, [2.5, 97.5])

    # 2x costs sensitivity (recompute net series)
    net2 = df["price_pnl"] + df["funding_pnl"] - 2.0 * df["costs"]
    mean_net2 = net2.mean()
    sharpe2 = (mean_net2 / net2.std(ddof=1) * math.sqrt(periods_per_year)) if net2.std(ddof=1) > 0 else 0.0

    # half-year subperiod stability
    df_h = df.set_index("t")
    sub = {}
    for label, lo, hi in [
        ("2022-11..2023-06", "2022-11-01", "2023-07-01"),
        ("2023-07..2023-12", "2023-07-01", "2024-01-01"),
        ("2024-01..2024-06", "2024-01-01", "2024-07-01"),
        ("2024-07..2024-12", "2024-07-01", "2025-01-01"),
        ("2025-01..2025-04", "2025-01-01", "2025-04-02"),
    ]:
        sel = df_h.loc[lo:hi, "net"]
        sub[label] = float(sel.mean()) if len(sel) else float("nan")

    # concentration: top-1 symbol share of total net PnL
    sym_tot = per_sym.sum()
    total_abs = sym_tot.abs().sum()
    top1_share = (sym_tot.abs().max() / total_abs) if total_abs > 0 else float("nan")
    top1_sym = sym_tot.abs().idxmax()

    return {
        "L": L, "H": H, "k": k, "n_periods": n,
        "mean_net_per_period": mean_net,
        "std_net_per_period": std_net,
        "total_net": total_net,
        "sharpe_annualized": sharpe,
        "max_drawdown": max_dd,
        "profit_factor": pf,
        "hit_rate": hit,
        "ci_lo": ci_lo, "ci_hi": ci_hi,
        "funding_total": df["funding_pnl"].sum(),
        "costs_total": df["costs"].sum(),
        "price_total": df["price_pnl"].sum(),
        "mean_net_2x_costs": mean_net2,
        "sharpe_2x_costs": sharpe2,
        "subperiods": sub,
        "top1_symbol": top1_sym,
        "top1_share": top1_share,
        "skew": float(df["net"].skew()),
        "kurtosis": float(df["net"].kurtosis()),
    }


def dsr(best, n_trials):
    """Deflated Sharpe Ratio (Lopez de Prado, AFML ch.8).

    PSR vs E[max SR] under null given n_trials independent trials.
    """
    n = best["n_periods"]
    sr = best["sharpe_annualized"]
    periods_per_year = (BARS_PER_DAY * DAYS_PER_YEAR) / best["H"]
    # per-period SR from annualized
    sr_period = sr / math.sqrt(periods_per_year)
    skew, kurt = best["skew"], best["kurtosis"]

    def var_sr(s):
        return (1.0 - skew * s + (kurt - 1.0) / 4.0 * s * s) / (n - 1)

    # expected max SR under null (Gaussian approx, Euler-Mascheroni gamma):
    # E[max] = sqrt(Var) * ((1-g)*Phi^-1(1-1/N) + g*Phi^-1(1-1/(N*e)))
    from statistics import NormalDist
    nd = NormalDist()
    gamma_ = 0.5772156649
    e_max_sr = math.sqrt(var_sr(0.0)) * (
        (1 - gamma_) * nd.inv_cdf(1 - 1.0 / n_trials)
        + gamma_ * nd.inv_cdf(1 - 1.0 / (n_trials * math.e))
    )
    var_best = var_sr(sr_period)
    if var_best <= 0:
        return 0.0, e_max_sr
    z = (sr_period - e_max_sr) / math.sqrt(var_best)
    return nd.cdf(z), e_max_sr


def main():
    print("Loading data ...")
    closes = load_close_matrix()
    funding = load_funding()
    print(f"Close matrix: {closes.shape[0]} bars x {closes.shape[1]} symbols, "
          f"{closes.index[0]} .. {closes.index[-1]}")

    ledger = []
    for L in GRID_L:
        for H in GRID_H:
            for k in GRID_K:
                r = run_trial(closes, funding, L, H, k)
                if r is None:
                    print(f"L={L} H={H} k={k}: insufficient data")
                    continue
                ledger.append(r)
                print(f"L={L:3d} H={H:2d} k={k}: n={r['n_periods']:4d} "
                      f"mean={r['mean_net_per_period']:+.5f} "
                      f"Sharpe={r['sharpe_annualized']:+.3f} "
                      f"PF={r['profit_factor']:.3f} "
                      f"CI=[{r['ci_lo']:+.5f},{r['ci_hi']:+.5f}] "
                      f"MaxDD={r['max_drawdown']:.4f}")

    n_trials = len(ledger)
    # DSR for each (needs best's skew/kurt; compute DSR per trial vs max-null)
    for r in ledger:
        d, e_max = dsr(r, n_trials)
        r["dsr"] = d
        r["e_max_sr_null"] = e_max

    # best by Sharpe among CI-passing, else by Sharpe overall
    passing = [r for r in ledger if r["ci_lo"] > 0 and r["profit_factor"] > 1]
    pool = passing if passing else ledger
    best = max(pool, key=lambda r: r["sharpe_annualized"])

    print("\n=== BEST ===")
    print(json.dumps({k: v for k, v in best.items() if k != "subperiods"},
                     default=str, indent=2))
    print("subperiods:", json.dumps(best["subperiods"], indent=2))

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "n_bars": int(closes.shape[0]),
        "n_symbols": int(closes.shape[1]),
        "ledger": ledger,
        "best": best,
        "n_passing_ci": len(passing),
    }
    (REPORT_DIR / "hyp_m002_results.json").write_text(
        json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
