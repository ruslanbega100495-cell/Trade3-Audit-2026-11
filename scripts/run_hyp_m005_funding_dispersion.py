"""HYP-M-005: cross-exchange funding dispersion — descriptive panel study (daily grid).

Registered BEFORE analysis: research/registry/HYP-M-005.yaml.

ВАЖНО про выравнивание: метки funding у бирж НЕ совпадают по фазе —
Bybit/HTX платят в 00/08/16 UTC, KuCoin в 04/12/20 UTC (смещение 4ч, период
аккруала сдвинут). Помарочное сравнение дало бы n=0. Корректная единица анализа
для carry-PnL — СУТОЧНАЯ СУММА funding (по 3 метки в сутках на каждой бирже):
позиция начисляет на собственном расписании каждой биржи, дневной спред
= сумма ставок дня на бирже A − сумма ставок дня на бирже B. Это точное
выражение дневного carry при неизменной позиции.

Окно: TRAIN 2024-01-01 -> 2025-04-01 (регистрация). Только descriptive.

Usage: .venv/Scripts/python.exe -X utf8 scripts/run_hyp_m005_funding_dispersion.py
Output: research/multi_exchange/BACKTESTS/hyp_m005_results.json
"""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

WIN_START = "2024-01-01"
WIN_END = "2025-04-01"
COST_BPS = 10.0   # round-trip taker 5+5 bps на СМЕНУ позиции (не на день)
RAW = Path("research/datasets/raw")
OUT = Path("research/multi_exchange/BACKTESTS/hyp_m005_results.json")

SOURCES = {
    "bybit": RAW / "bybit/BTCUSDT/funding/2024-01-01_2026-09-30.json",
    "kucoin": RAW / "kucoin/BTCUSDT/funding/2024-01-01_2026-11-09.json",
    "htx": RAW / "htx/BTCUSDT/funding/2024-01-01_2026-11-09.json",
}


def load_series(path: Path) -> pd.Series:
    d = json.load(open(path))
    if "funding" in d:                       # kucoin/htx collector format
        rows = d["funding"]
        s = pd.Series({pd.Timestamp(r["timestamp"]).tz_convert("UTC"): float(r["funding_rate"])
                       for r in rows})
    else:                                    # bybit format: records/timestamp_ms
        s = pd.Series({pd.to_datetime(r["timestamp_ms"], unit="ms", utc=True):
                       float(r["funding_rate"]) for r in d["records"]})
    return s.sort_index()


def daily_sums(s: pd.Series) -> pd.Series:
    """Суточная сумма funding (bps/day); только полные сутки (ровно 3 метки)."""
    df = s.to_frame("r")
    df["day"] = df.index.floor("D")
    g = df.groupby("day")["r"].agg(["sum", "count"])
    g = g[g["count"] == 3]
    return g["sum"] * 1e4


def ar1_adf_proxy(x: np.ndarray) -> float:
    """AR(1)-proxy стационарности: H0 unit root; возвращает одностороннюю
    нормальную аппроксимацию p-value для beta<1. НЕ полноценный ADF —
    ограничение зафиксировано в отчёте."""
    v = np.asarray(x, dtype=float)
    if len(v) < 50:
        return float("nan")
    d = np.diff(v)
    lag = v[:-1] - v[:-1].mean()
    denom = lag @ lag
    if denom == 0:
        return float("nan")
    beta = (d @ lag) / denom
    resid = d - beta * lag
    se = math.sqrt(max((resid @ resid) / max(len(d) - 2, 1) / denom, 1e-18))
    t = (beta - 1) / se
    return float(0.5 * (1 + math.erf(t / math.sqrt(2))))


def half_life_days(x: np.ndarray) -> float:
    v = np.asarray(x, dtype=float)
    if len(v) < 50:
        return float("nan")
    d = np.diff(v)
    lag = v[:-1]
    lag_c = lag - lag.mean()
    denom = lag_c @ lag_c
    if denom == 0:
        return float("inf")
    beta = (d @ lag_c) / denom
    if beta >= 0:
        return float("inf")
    return float(-math.log(2) / beta)  # в днях


def pair_stats(a: pd.Series, b: pd.Series, name_a: str, name_b: str) -> dict:
    da, db = daily_sums(a), daily_sums(b)
    df = pd.DataFrame({"a": da, "b": db}).dropna()
    df = df[(df.index >= pd.Timestamp(WIN_START, tz="UTC")) &
            (df.index < pd.Timestamp(WIN_END, tz="UTC"))]
    spread = df["a"] - df["b"]  # bps/day
    n = len(spread)
    if n < 200:
        return {"pair": f"{name_a}-{name_b}", "n_days": n, "verdict": "INSUFFICIENT"}
    v = spread.to_numpy()
    m, sd = float(v.mean()), float(v.std(ddof=1))
    se = sd / math.sqrt(n)
    ci = (m - 1.96 * se, m + 1.96 * se)
    abs_s = np.abs(v)
    sign = np.sign(v)
    flips = float((np.diff(sign) != 0).mean())
    hl = half_life_days(v)
    adf = ar1_adf_proxy(v)
    # экономика: позиция платит round-trip ТОЛЬКО при смене знака спреда.
    # gross = sum|spread| (bps/день суммарно при идеальном следовании знаку);
    # cost = flips * COST_BPS / n_days.
    n_flips = int((np.diff(sign) != 0).sum())
    gross_if_follow_bps = float(abs_s.sum())          # за всё окно
    cost_of_flips_bps = n_flips * COST_BPS
    return {
        "pair": f"{name_a}-{name_b}", "n_days": n,
        "mean_spread_bps_day": round(m, 3), "std_bps_day": round(sd, 3),
        "ci95": [round(ci[0], 3), round(ci[1], 3)],
        "mean_abs_bps_day": round(float(abs_s.mean()), 3),
        "p95_abs_bps_day": round(float(np.quantile(abs_s, 0.95)), 3),
        "share_days_gt_10bps": round(float((abs_s > COST_BPS).mean()), 4),
        "sign_persistence": round(1 - flips, 4),
        "n_flips": n_flips,
        "autocorr_lag1": round(float(pd.Series(v).autocorr(1)), 4),
        "half_life_days": round(hl, 2) if math.isfinite(hl) else "inf",
        "adf_ar1_proxy_pvalue": round(adf, 5) if adf == adf else "nan",
        "economics_bps_per_window": {
            "gross_if_follow_sign": round(gross_if_follow_bps, 1),
            "flip_cost_total": round(cost_of_flips_bps, 1),
            "net_if_follow_sign": round(gross_if_follow_bps - cost_of_flips_bps, 1),
            "avg_net_bps_day": round((gross_if_follow_bps - cost_of_flips_bps) / n, 3),
        },
        "direction_note": f"positive = {name_a} funding higher (short {name_a} / long {name_b} harvests)",
    }


def main():
    series, meta = {}, {}
    for vname, p in SOURCES.items():
        if not p.exists():
            print(f"WARN missing: {p}")
            continue
        s = load_series(p)
        series[vname] = s
        ds = daily_sums(s)
        meta[vname] = {
            "file": str(p).replace(chr(92), "/"),
            "n_marks": int(len(s)),
            "n_days_full": int(len(ds)),
            "window_days": int(((ds.index >= pd.Timestamp(WIN_START, tz="UTC")) &
                                (ds.index < pd.Timestamp(WIN_END, tz="UTC"))).sum()),
            "dups": int(s.index.duplicated().sum()),
        }
    print("coverage:", json.dumps(meta, indent=1))
    res = {"window": [WIN_START, WIN_END], "cost_floor_bps": COST_BPS,
           "unit": "daily funding sum (bps/day); 3 marks/day/venue; kucoin marks offset 4h (04/12/20 UTC)",
           "coverage": meta, "pairs": {}}
    for a, b in [("bybit", "kucoin"), ("bybit", "htx"), ("kucoin", "htx")]:
        if a in series and b in series:
            st = pair_stats(series[a], series[b], a, b)
            res["pairs"][st["pair"]] = st
            print(json.dumps(st, indent=1))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump(res, open(OUT, "w"), indent=2)
    print(f"saved -> {OUT}")


if __name__ == "__main__":
    main()
