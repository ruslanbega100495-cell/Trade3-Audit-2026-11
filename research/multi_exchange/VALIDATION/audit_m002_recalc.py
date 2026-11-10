"""
RED TEAM AUDIT — HYP-M-002 cross-sectional momentum, independent recalc.
Independent reimplementation (different code path, own bootstrap seed)
for: best combo L=24,H=12,k=3 (full metric set + decomposition + DSR),
a H=4 spot-check combo L=24,H=4,k=3, and funding data sanity checks.

Run: .venv/Scripts/python.exe -X utf8 research/multi_exchange/VALIDATION/audit_m002_recalc.py
"""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "research/datasets/raw/bybit"

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
    "ADAUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT", "LTCUSDT", "BCHUSDT",
    "NEARUSDT", "UNIUSDT", "TRXUSDT", "XLMUSDT", "XMRUSDT", "AAVEUSDT",
    "CRVUSDT", "OPUSDT", "APTUSDT", "INJUSDT", "HBARUSDT", "STXUSDT",
    "ZECUSDT",
]
COST = 0.00055 + 0.00050  # per side


def load():
    closes = {}
    for sym in SYMBOLS:
        d = json.loads((DATA / sym / "H4" / "2022-11-01_2025-04-01.json").read_text())
        idx = pd.to_datetime([c["open_time"] for c in d["candles"]])
        closes[sym] = pd.Series([float(c["close"]) for c in d["candles"]], index=idx)
    px = pd.DataFrame(closes).sort_index()
    px = px[~px.index.duplicated(keep="last")].dropna()

    fund = {}
    grid_off = 0
    tot_pos = tot = 0
    for sym in SYMBOLS:
        d = json.loads((DATA / sym / "funding" / "2022-11-01_2025-04-01.json").read_text())
        recs = d["records"]
        idx = pd.to_datetime([r["timestamp_iso"] for r in recs])
        vals = np.array([float(r["funding_rate"]) for r in recs])
        fund[sym] = pd.Series(vals, index=idx).sort_index()
        grid_off += int((fund[sym].index.hour % 4 != 0).sum())
        tot_pos += int((vals > 0).sum()); tot += len(vals)
    print(f"close matrix: {px.shape[0]} bars x {px.shape[1]} symbols")
    print(f"funding: events off H4 grid (hour%4!=0): {grid_off}; P(rate>0)={tot_pos/tot:.3f}")
    return px, fund


def run(px, fund, L, H, k, seed=1234, n_boot=10000):
    rets = px.pct_change()
    mom = px / px.shift(L) - 1.0
    fa = {s: fund[s].reindex(px.index).ffill() for s in px.columns}
    syms = list(px.columns)
    n = len(px)
    rows = []
    t = L
    while t + H < n:
        sig = mom.iloc[t].dropna().sort_values()
        if len(sig) < len(syms):
            t += H; continue
        shorts = list(sig.index[:k]); longs = list(sig.index[-k:])
        w = pd.Series(0.0, index=syms)
        w[longs] = 1.0 / (2 * k); w[shorts] = -1.0 / (2 * k)
        price = fund_pnl = 0.0
        for h in range(1, H + 1):
            bar_ret = rets.iloc[t + h]
            price += float((w * bar_ret).sum())
            ts = px.index[t + h]
            if ts.hour in (0, 8, 16):
                for s in longs + shorts:
                    fr = fa[s].iloc[t + h]
                    if not np.isnan(fr):
                        fund_pnl += -w[s] * fr  # long pays fr>0, short receives
        rows.append((px.index[t], price, fund_pnl, price + fund_pnl - 2 * COST))
        t += H

    df = pd.DataFrame(rows, columns=["t", "price", "fund", "net"]).set_index("t")
    m = df["net"]
    ppy = 6 * 365 / H
    sharpe = m.mean() / m.std(ddof=1) * math.sqrt(ppy)
    cum = np.concatenate([[0.0], m.cumsum().to_numpy()])
    mdd = float(np.max(np.maximum.accumulate(cum) - cum))
    gains = m[m > 0].sum(); losses = -m[m < 0].sum()
    pf = gains / losses

    # block bootstrap CI — independent implementation/seed
    rng = np.random.default_rng(seed)
    x = m.to_numpy(); nn = len(x); blk = max(2, int(math.sqrt(nn)))
    means = np.empty(n_boot)
    for b in range(n_boot):
        starts = rng.integers(0, nn, size=int(np.ceil(nn / blk)) + 1)
        chunks = []
        for s in starts:
            chunks.append(np.roll(x, -s)[:blk])
        means[b] = np.concatenate(chunks)[:nn].mean()
    ci = np.percentile(means, [2.5, 97.5])

    net2 = df["price"] + df["fund"] - 2 * 2 * COST
    sharpe2 = net2.mean() / net2.std(ddof=1) * math.sqrt(ppy)

    # DSR per AFML ch.8 with this trial's own skew/kurt
    from statistics import NormalDist
    nd = NormalDist(); gam = 0.5772156649
    sr_p = sharpe / math.sqrt(ppy)
    sk = float(m.skew()); ku = float(m.kurtosis())

    def var_sr(s):
        return (1 - sk * s + (ku - 1) / 4 * s * s) / (nn - 1)
    e_max = math.sqrt(var_sr(0.0)) * ((1 - gam) * nd.inv_cdf(1 - 1 / 12)
                                      + gam * nd.inv_cdf(1 - 1 / (12 * math.e)))
    vb = var_sr(sr_p)
    dsr = nd.cdf((sr_p - e_max) / math.sqrt(vb)) if vb > 0 else 0.0

    subs = {}
    for label, lo, hi in [("22-11..23-06", "2022-11-01", "2023-07-01"),
                          ("23-07..23-12", "2023-07-01", "2024-01-01"),
                          ("24-01..24-06", "2024-01-01", "2024-07-01"),
                          ("24-07..24-12", "2024-07-01", "2025-01-01"),
                          ("25-01..25-04", "2025-01-01", "2025-04-02")]:
        subs[label] = float(m.loc[lo:hi].mean())

    print(f"\n[L={L} H={H} k={k}] n={nn} mean={m.mean()*100:+.4f}%/period Sharpe={sharpe:.3f} "
          f"PF={pf:.3f} hit={(m>0).mean():.3f}")
    print(f"  CI95 boot=[{ci[0]*100:+.4f},{ci[1]*100:+.4f}] MaxDD={mdd*100:.2f}% "
          f"Total net={m.sum()*100:+.2f}%")
    print(f"  price={df['price'].sum()*100:+.2f}% fund={df['fund'].sum()*100:+.2f}% "
          f"costs={df['net'].sub(df['price']+df['fund']).sum()*100:+.2f}%")
    print(f"  2x: mean={net2.mean()*100:+.4f}% Sharpe={sharpe2:.3f}")
    print(f"  DSR={dsr:.3f} (e_max_null={e_max:.5f}/period, sr_period={sr_p:.5f}, skew={sk:.2f}, kurt={ku:.2f})")
    print(f"  subperiods: " + ", ".join(f"{k_}={v*100:+.3f}%" for k_, v in subs.items()))
    return df


px, fund = load()
run(px, fund, 24, 12, 3)
run(px, fund, 96, 12, 3)
run(px, fund, 24, 4, 3)
