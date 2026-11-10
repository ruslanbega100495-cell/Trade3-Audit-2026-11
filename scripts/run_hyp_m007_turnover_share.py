"""HYP-M-007: tier-2 turnover-share rotation (BTC H1, 6 venues, exploratory TRAIN).

Registered BEFORE analysis: research/registry/HYP-M-007.yaml.
Usage: .venv/Scripts/python.exe -X utf8 scripts/run_hyp_m007_turnover_share.py
"""
import json
import math
from pathlib import Path

import pandas as pd

WIN_END = "2025-04-01"
TIER2 = ["kucoin", "htx", "weex", "bingx"]
LEADERS = ["bybit", "okx"]
VENUES = LEADERS + TIER2
OUT = Path("research/multi_exchange/BACKTESTS/hyp_m007_results.json")


def load_turnover(v):
    f = sorted((Path("research/datasets/raw") / v / "BTCUSDT" / "H1").glob("*.json"))[-1]
    d = json.load(open(f))
    df = pd.DataFrame(d["candles"])
    df["ts"] = pd.to_datetime(df["open_time"]).dt.tz_convert("UTC")
    base = df["turnover"] if "turnover" in df.columns else df["volume"]
    s = pd.Series(pd.to_numeric(base, errors="coerce").values, index=df["ts"])
    return s.sort_index()


def load_close(v):
    f = sorted((Path("research/datasets/raw") / v / "BTCUSDT" / "H1").glob("*.json"))[-1]
    d = json.load(open(f))
    df = pd.DataFrame(d["candles"])
    df["ts"] = pd.to_datetime(df["open_time"]).dt.tz_convert("UTC")
    return pd.Series(pd.to_numeric(df["close"], errors="coerce").values,
                     index=df["ts"]).sort_index()


def t_stat(a, b):
    if len(a) < 5 or len(b) < 5:
        return float("nan")
    se = math.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    return float((a.mean() - b.mean()) / se) if se > 0 else float("nan")


def main():
    t = {v: load_turnover(v) for v in VENUES}
    closes = pd.DataFrame({v: load_close(v) for v in LEADERS})
    df = pd.DataFrame(t)
    df = df[df[LEADERS].notna().all(axis=1)]  # лидеры обязаны быть
    mid = closes[LEADERS].median(axis=1)
    fwd = {h: mid.shift(-h) / mid - 1 for h in [1, 4, 24]}
    tier2_sum = df[TIER2].sum(axis=1, min_count=1)
    total = tier2_sum + df[LEADERS].sum(axis=1)
    share = (tier2_sum / total).dropna()
    # z-score rolling 60 дней
    z = (share - share.rolling(60 * 24).mean()) / share.rolling(60 * 24).std()
    df2 = pd.DataFrame({"z": z})
    for h in [1, 4, 24]:
        df2[f"fwd{h}"] = fwd[h]
    df2 = df2.dropna()
    df2 = df2[df2.index < pd.Timestamp(WIN_END, tz="UTC")]
    df2 = df2[df2.index >= pd.Timestamp("2024-08-01", tz="UTC")]  # прогрев z-окна
    print(f"n bars: {len(df2)} ({df2.index[0]} -> {df2.index[-1]})")
    df2["q"] = pd.qcut(df2["z"], 4, labels=["Q1", "Q2", "Q3", "Q4"])
    res = {"n": int(len(df2))}
    for h in [1, 4, 24]:
        g = df2.groupby("q", observed=True)[f"fwd{h}"].mean()
        t_ = t_stat(df2[df2["q"] == "Q4"][f"fwd{h}"], df2[df2["q"] == "Q1"][f"fwd{h}"])
        rho = df2["z"].corr(df2[f"fwd{h}"], method="spearman")
        res[f"h{h}"] = {
            "mean_fwd_bps_by_q": {k: round(float(v) * 1e4, 2) for k, v in g.items()},
            "q4_minus_q1_bps": round(float((g["Q4"] - g["Q1"]) * 1e4), 2),
            "t": round(t_, 2) if t_ == t_ else "nan",
            "spearman": round(float(rho), 4),
        }
        print(f"h{h}: {json.dumps(res[f'h{h}'])}")
    json.dump(res, open(OUT, "w"), indent=2)
    print(f"saved -> {OUT}")


if __name__ == "__main__":
    main()
