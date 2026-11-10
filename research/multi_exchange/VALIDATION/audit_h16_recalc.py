"""
RED TEAM AUDIT — HYP-H16 validation, independent recalculation.
Reimplements the frozen-config validation from raw data with an
independent code path (pandas), plus an order-of-magnitude estimate of
the omitted funding cost using actual Bybit BTC funding history.

Run: .venv/Scripts/python.exe -X utf8 research/multi_exchange/VALIDATION/audit_h16_recalc.py
"""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "research/datasets/raw/bybit/BTCUSDT/H4/2024-01-01_2026-09-30.json"
FUND = ROOT / "research/datasets/raw/bybit/BTCUSDT/funding/2024-01-01_2026-09-30.json"

N, TAKER, SLIP = 12, 0.00055, 0.00050
TARGET_VOL, LEV_CAP, VOL_W, MIN_VOL = 0.20, 2.0, 20, 0.05
VAL_START, VAL_END, WARM_START = "2025-04-01", "2025-10-01", "2025-03-01"


def build_trades(cost_mult=1.0):
    d = json.load(open(DATA))
    assert d.get("dataset_hash") == "e182346101e28d26", d.get("dataset_hash")
    df = pd.DataFrame(d["candles"])
    df["open_time"] = df["open_time"].astype(str)
    df = df[(df["open_time"].str[:10] >= WARM_START) & (df["open_time"].str[:10] < VAL_END)]
    df = df.reset_index(drop=True)
    close = df["close"].astype(float).to_numpy()
    opn = df["open"].astype(float).to_numpy()
    n = len(df)

    t0 = int(np.argmax(df["open_time"].str[:10].to_numpy() >= VAL_START))
    trades = []
    t = t0
    while t < n - N - 1:
        # signal identical in math to author's: uses closes[t-N..t], vol from
        # log returns of closes[t-19..t]
        if t >= N + VOL_W:
            ret_n = close[t] / close[t - N] - 1.0
            direction = 1.0 if ret_n > 0 else -1.0
            lr = np.log(close[t - np.arange(VOL_W)] / close[t - np.arange(VOL_W) - 1])
            rvol = lr.std(ddof=1) * math.sqrt(252 * 6)
            if rvol >= MIN_VOL:
                pos = direction * TARGET_VOL / rvol
                pos = min(LEV_CAP, max(-LEV_CAP, pos))
                ei, xi = t + 1, t + 1 + N
                pr = (opn[xi] - opn[ei]) / opn[ei]
                net = pos * pr - abs(pos) * (TAKER + SLIP) * cost_mult * 2
                trades.append(dict(entry=df["open_time"].iat[ei], exit=df["open_time"].iat[xi],
                                   direction=int(direction), pos=pos, net=net))
        t += N
    return pd.DataFrame(trades), n, t0


def metrics(tr, by="entry"):
    r = tr["net"].to_numpy()
    daily = tr.groupby(tr[by].str[:10])["net"].sum()
    sharpe = daily.mean() / daily.std(ddof=1) * math.sqrt(252)
    cum = np.cumsum(r)
    mdd = float(np.max(np.maximum.accumulate(np.concatenate([[0.0], cum])) - np.concatenate([[0.0], cum])))
    from scipy import stats
    tcrit = stats.t.ppf(0.975, len(r) - 1)
    half = tcrit * r.std(ddof=1) / math.sqrt(len(r))
    gp = r[r > 0].sum()
    gl = -r[r < 0].sum()
    return dict(n=len(r), mean=r.mean() * 100, ci=[(r.mean() - half) * 100, (r.mean() + half) * 100],
                sharpe=sharpe, mdd=mdd * 100, total=r.sum() * 100, pf=gp / gl, wr=(r > 0).mean(),
                n_long=int((tr["direction"] > 0).sum()))


def funding_impact(tr):
    """Actual funding PnL over the validation trades, using real Bybit
    funding history. Convention: long pays positive rate, short receives.
    Funding events every 8h. PnL = -position * rate per event (position>0 long).
    Notional = |position| (price return already scaled by position)."""
    fd = json.load(open(FUND))
    recs = fd["records"] if isinstance(fd, dict) and "records" in fd else fd
    ts = pd.to_datetime([r.get("timestamp_iso") or r.get("time") for r in recs])
    rates = np.array([float(r["funding_rate"]) for r in recs])
    fs = pd.Series(rates, index=ts).sort_index()
    print(f"  funding records: {len(fs)}, mean={fs.mean():.3e}, "
          f"P(rate>0)={float((fs > 0).mean()):.3f}, range {fs.index[0]} .. {fs.index[-1]}")

    total = 0.0
    per_trade = []
    for _, row in tr.iterrows():
        e = pd.Timestamp(row["entry"])
        x = pd.Timestamp(row["exit"])
        # events with timestamp in (entry, exit]
        ev = fs.loc[(fs.index > e) & (fs.index <= x)]
        fp = float(-(row["pos"]) * ev.sum())  # long pays positive rate
        total += fp
        per_trade.append(fp)
    tr = tr.copy()
    tr["fund_pnl"] = per_trade
    return total, tr


tr, n_bars, t0 = build_trades()
n_val = int((pd.Series(tr["entry"]).str[:10] >= VAL_START).sum())
print(f"bars total(warmup+val)={n_bars}, validation bars={n_bars - t0}, trades={len(tr)}")

for label, mult in [("base", 1.0), ("2x", 2.0)]:
    t_, _, _ = build_trades(cost_mult=mult)
    m = metrics(t_)
    print(f"\n[{label}] n={m['n']} LONG={m['n_long']} mean={m['mean']:+.4f}% "
          f"CI=[{m['ci'][0]:+.4f},{m['ci'][1]:+.4f}] Sharpe={m['sharpe']:.3f} "
          f"MaxDD={m['mdd']:.4f}% PF={m['pf']:.3f} WR={m['wr']:.3f} Total={m['total']:+.4f}%")

# N=24 exploratory
N = 24
tr24, _, _ = build_trades()
m = metrics(tr24)
print(f"\n[N=24 expl] n={m['n']} mean={m['mean']:+.4f}% CI=[{m['ci'][0]:+.4f},{m['ci'][1]:+.4f}] "
      f"Sharpe={m['sharpe']:.3f} MaxDD={m['mdd']:.4f}% PF={m['pf']:.3f} WR={m['wr']:.3f} Total={m['total']:+.4f}%")
N = 12

# funding omission estimate
tot, tr_f = funding_impact(build_trades()[0])
print(f"\n[FUNDING ESTIMATE] actual net funding over validation trades: {tot * 100:+.4f}% "
      f"(sum, on top of reported Total)")
m = metrics(tr_f.assign(net=tr_f["net"] + tr_f["fund_pnl"]))
print(f"  with funding: mean={m['mean']:+.4f}% CI=[{m['ci'][0]:+.4f},{m['ci'][1]:+.4f}] "
      f"Sharpe={m['sharpe']:.3f} Total={m['total']:+.4f}%")

# rough symmetric bound: if all positions were long at |pos|=1 the whole time
d0, d1 = pd.Timestamp("2025-04-01", tz="UTC"), pd.Timestamp("2025-10-01", tz="UTC")
ev = pd.Series(np.array([float(r["funding_rate"]) for r in (json.load(open(FUND))["records"])]),
               index=pd.to_datetime([r["timestamp_iso"] for r in json.load(open(FUND))["records"]]))
ev = ev.sort_index().loc[d0:d1]
print(f"  bound: sum of all funding events 2025-04..2025-10 = {ev.sum() * 100:+.4f}% per unit notional; "
      f"avg |pos| in audit = {tr['pos'].abs().mean():.3f}")
