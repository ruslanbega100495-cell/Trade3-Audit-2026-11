"""HYP-M-001: cross-exchange price dislocation event study (BTCUSDT H1, 6 venues).

Registered BEFORE any analysis: research/registry/HYP-M-001.yaml.
Descriptive event study per registration; no trading-backtest claims.

Usage: .venv/Scripts/python.exe -X utf8 scripts/run_hyp_m001_dislocation.py
Output: research/multi_exchange/BACKTESTS/hyp_m001_results.json
"""
import json
import math
from pathlib import Path

import pandas as pd

RAW = Path("research/datasets/raw")
VENUES = ["bybit", "okx", "kucoin", "htx", "weex", "bingx"]
LEADERS = ["bybit", "okx"]
THRESHOLDS_BPS = [10, 25, 50, 100]
HORIZONS = [1, 2, 4]
PERSIST_MIN_BARS = 2
COST_BPS = 10.0          # round-trip taker 5+5 bps per registration
OUT = Path("research/multi_exchange/BACKTESTS/hyp_m001_results.json")


def load_closes() -> pd.DataFrame:
    cols = {}
    meta = {}
    for v in VENUES:
        files = sorted((RAW / v / "BTCUSDT" / "H1").glob("*.json"))
        if not files:
            print(f"WARN: no H1 data for {v}")
            continue
        d = json.load(open(files[-1]))
        meta[v] = {
            "file": str(files[-1]),
            "start": d["start"], "end": d["end"],
            "record_count": d["record_count"], "dataset_hash": d["dataset_hash"],
        }
        s = pd.Series(
            {pd.Timestamp(c["open_time"]): float(c["close"]) for c in d["candles"]}
        )
        s.index = s.index.tz_convert("UTC")
        cols[v] = s
    df = pd.DataFrame(cols).sort_index()
    # gap diagnostics per venue
    for v in df.columns:
        idx = df.index[df[v].notna()]
        if len(idx) > 1:
            gaps = pd.Series(idx).diff().dt.total_seconds().div(3600)
            meta[v]["gaps_gt_2h"] = int((gaps > 2).sum())
            meta[v]["n_bars"] = int(len(idx))
    return df, meta


def event_study(df: pd.DataFrame) -> dict:
    leaders = df[LEADERS].median(axis=1)  # median of available leaders
    res = {"thresholds": {}, "disp_distribution_bps": {}, "pairwise_overlap": {}}
    n = len(df)

    # overlap: bars where both venues have data
    for a in VENUES:
        for b in VENUES:
            if a < b and a in df and b in df:
                res["pairwise_overlap"][f"{a}-{b}"] = int(
                    (df[a].notna() & df[b].notna()).sum())

    for v in VENUES:
        if v not in df or v in LEADERS:
            continue
        disp = (df[v] / leaders - 1.0) * 1e4  # bps, NaN when venue or leaders missing
        ad = disp.abs()
        res["disp_distribution_bps"][v] = {
            "n": int(ad.notna().sum()),
            "median": round(float(ad.median()), 2),
            "p90": round(float(ad.quantile(0.90)), 2),
            "p99": round(float(ad.quantile(0.99)), 2),
            "max": round(float(ad.max()), 2),
        }
        for th in THRESHOLDS_BPS:
            over = (ad >= th).fillna(False).to_numpy()
            # runs of >= PERSIST_MIN_BARS consecutive True
            events = []
            i = 0
            while i < n:
                if over[i]:
                    j = i
                    while j + 1 < n and over[j + 1]:
                        j += 1
                    if j - i + 1 >= PERSIST_MIN_BARS:
                        events.append((i, j))
                    i = j + 1
                else:
                    i += 1
            # one event = entry at last bar of run (t), measure convergence forward
            stats = {h: [] for h in HORIZONS}
            months = set()
            n_up = 0  # events where venue below leader (disp<0) -> expect venue up
            for (i, j) in events:
                t = j  # last bar of persistent run; signal known at close[t]
                d0 = disp.iloc[t]
                if pd.isna(d0):
                    continue
                months.add(str(disp.index[t])[:7])
                for h in HORIZONS:
                    if t + h >= n:
                        continue
                    conv = float(disp.iloc[t] - disp.iloc[t + h])  # bps correction
                    if not math.isnan(conv):
                        stats[h].append(conv)
                if d0 < 0:
                    n_up += 1
            out = {"n_events": len(events), "n_months": len(months),
                   "months": sorted(months), "n_disp_negative": n_up}
            for h in HORIZONS:
                xs = pd.Series(stats[h], dtype=float).dropna()
                if len(xs) < 5:
                    out[f"h{h}"] = {"n": int(len(xs))}
                    continue
                m = float(xs.mean())
                sd = float(xs.std(ddof=1))
                se = sd / math.sqrt(len(xs))
                tcrit = 1.96 if len(xs) >= 30 else 4.303  # approx t(0.025, inf/30)
                ci = (m - tcrit * se, m + tcrit * se)
                net = m - COST_BPS
                out[f"h{h}"] = {
                    "n": int(len(xs)),
                    "mean_correction_bps": round(m, 2),
                    "ci95": [round(ci[0], 2), round(ci[1], 2)],
                    "mean_net_of_cost_bps": round(net, 2),
                    "mean_net_2x_cost_bps": round(m - 2 * COST_BPS, 2),
                    "hit_rate_correction_positive": round(float((xs > 0).mean()), 4),
                    "median_correction_bps": round(float(xs.median()), 2),
                }
            res["thresholds"].setdefault(str(th), {})[v] = out
    return res


def main():
    df, meta = load_closes()
    print(f"matrix: {df.shape[0]} timestamps x {df.shape[1]} venues "
          f"({df.index[0]} -> {df.index[-1]})")
    res = {"coverage": meta, "n_timestamps": int(len(df)),
           "leader_overlap_bars": int(df[LEADERS].notna().all(axis=1).sum())}
    res.update(event_study(df))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump(res, open(OUT, "w"), indent=2)
    print(f"saved -> {OUT}")

    # console digest
    print("\n=== |dislocation| distribution (bps), vs leader median ===")
    for v, d in res["disp_distribution_bps"].items():
        print(f"  {v:7s} n={d['n']:6d} median={d['median']:7.2f} p90={d['p90']:8.2f} "
              f"p99={d['p99']:9.2f} max={d['max']:10.2f}")
    print("\n=== events (persist>=2 bars) ===")
    for th, venues in res["thresholds"].items():
        for v, o in venues.items():
            h4 = o.get("h4", {})
            print(f"  th={th:>3s}bps {v:7s} events={o['n_events']:5d} months={o['n_months']:2d} "
                  f"h4: n={h4.get('n', 0):5d} mean={h4.get('mean_correction_bps', 'NA')} "
                  f"net={h4.get('mean_net_of_cost_bps', 'NA')} CI={h4.get('ci95', 'NA')}")


if __name__ == "__main__":
    main()
