"""HYP-M-006: OI-delta lead exploratory study (BTCUSDT H4, Bybit, TRAIN window).

Registered BEFORE analysis: research/registry/HYP-M-006.yaml.
Exploratory single pass; kill criterion |t|<3 or effect < 2x round trip (42 bps).

Usage: .venv/Scripts/python.exe -X utf8 scripts/run_hyp_m006_oi_lead.py
Output: research/multi_exchange/BACKTESTS/hyp_m006_results.json
"""
import json
import math
from pathlib import Path

import pandas as pd

WIN_START = "2024-01-01"
WIN_END = "2025-04-01"
RAW = Path("research/datasets/raw/bybit/BTCUSDT/H4")
OI_FILE = RAW / "oi_2024-01-01_2026-09-30.json"
KLINE_FILE = RAW / "2024-01-01_2026-09-30.json"
OUT = Path("research/multi_exchange/BACKTESTS/hyp_m006_results.json")


def load_klines():
    d = json.load(open(KLINE_FILE))
    assert d.get("dataset_hash") == "e182346101e28d26", d.get("dataset_hash")
    df = pd.DataFrame(d["candles"])
    df["ts"] = pd.to_datetime(df["open_time"]).dt.tz_convert("UTC")
    df = df.set_index("ts")
    for c in ["open", "high", "low", "close", "volume", "turnover"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def load_oi():
    d = json.load(open(OI_FILE))
    rows = d.get("records") or d.get("oi") or d.get("data") or []
    if isinstance(rows, dict):
        rows = rows.get("list") or rows.get("records") or []
    if rows and "timestamp_ms" in rows[0]:
        s = pd.Series({pd.to_datetime(r["timestamp_ms"], unit="ms", utc=True):
                       float(r["open_interest"]) for r in rows})
    else:
        ts_col = "timestamp" if rows and "timestamp" in rows[0] else "time"
        oi_col = "open_interest" if rows and "open_interest" in rows[0] else "oi"
        s = pd.Series({pd.Timestamp(r[ts_col]).tz_convert("UTC"): float(r[oi_col]) for r in rows})
    return s.sort_index()


def t_stat(a, b):
    n1, n2 = len(a), len(b)
    if n1 < 5 or n2 < 5:
        return float("nan")
    m1, m2 = a.mean(), b.mean()
    v1, v2 = a.var(ddof=1), b.var(ddof=1)
    se = math.sqrt(v1 / n1 + v2 / n2)
    if se == 0:
        return float("nan")
    return float((m1 - m2) / se)


def main():
    px = load_klines()
    oi = load_oi()
    df = px.join(pd.DataFrame({"oi": oi}), how="inner")
    df = df[(df.index >= pd.Timestamp(WIN_START, tz="UTC")) &
            (df.index < pd.Timestamp(WIN_END, tz="UTC"))].copy()
    print(f"joined bars: {len(df)} ({df.index[0]} -> {df.index[-1]})")

    # turnover в $ за бар; delta OI нормирована оборотом
    df["d_oi"] = df["oi"].diff()
    df["d_oi_norm"] = df["d_oi"] / df["turnover"].replace(0, float("nan"))
    df["ret_fwd_1"] = df["close"].shift(-1) / df["close"] - 1
    df["ret_fwd_4"] = df["close"].shift(-4) / df["close"] - 1
    df["ret_fwd_24"] = df["close"].shift(-24) / df["close"] - 1
    df = df.dropna(subset=["d_oi_norm", "ret_fwd_1", "ret_fwd_4", "ret_fwd_24"])

    # квартильная группировка + контрасты Q4 vs Q1
    df["q"] = pd.qcut(df["d_oi_norm"], 4, labels=["Q1", "Q2", "Q3", "Q4"])
    res = {"n_bars": int(len(df)), "window": [WIN_START, WIN_END],
           "quartile_bounds": [float(x) for x in
                               df["d_oi_norm"].quantile([0.25, 0.5, 0.75]).tolist()],
           "horizons": {}}
    for h, col in [("1h", "ret_fwd_1"), ("4h", "ret_fwd_4"), ("24h", "ret_fwd_24")]:
        g = df.groupby("q", observed=True)[col].agg(["mean", "std", "count"])
        q1, q4 = g.loc["Q1", "mean"], g.loc["Q4", "mean"]
        t = t_stat(df[df["q"] == "Q4"][col], df[df["q"] == "Q1"][col])
        # взаимодействие со знаком цены: сплит по знаку прошлого бара
        df["up"] = (df["close"] > df["open"])
        inter = {}
        for side, sub in [("up_bar", df[df["up"]]), ("down_bar", df[~df["up"]])]:
            if len(sub) > 30:
                gi = sub.groupby("q", observed=True)[col].mean()
                inter[side] = {k: round(float(v), 6) for k, v in gi.items()}
        res["horizons"][h] = {
            "mean_fwd_ret_by_quartile": {k: round(float(v), 6) for k, v in g["mean"].items()},
            "q4_minus_q1_bps": round(float((q4 - q1) * 1e4), 2),
            "t_q4_vs_q1": round(t, 3) if t == t else "nan",
            "by_bar_direction": inter,
        }
        print(f"\n=== {h}: Q4-Q1 = {(q4-q1)*1e4:.2f} bps, t = {t:.2f}")
        print(g.round(6).to_string())

    # монотонность по квантилям (спирменовская rho d_oi_norm vs fwd ret)
    for h, col in [("1h", "ret_fwd_1"), ("4h", "ret_fwd_4"), ("24h", "ret_fwd_24")]:
        rho = df["d_oi_norm"].corr(df[col], method="spearman")
        res.setdefault("spearman", {})[h] = round(float(rho), 4)
        print(f"spearman(d_oi_norm, fwd {h}) = {rho:.4f}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump(res, open(OUT, "w"), indent=2)
    print(f"\nsaved -> {OUT}")


if __name__ == "__main__":
    main()
