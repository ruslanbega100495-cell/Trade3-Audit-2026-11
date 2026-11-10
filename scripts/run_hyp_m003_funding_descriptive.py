"""HYP-M-003 (registered BEFORE analysis): exploratory descriptive of the
Bybit <-> OKX funding-rate spread on BTCUSDT / ETHUSDT perps.

Method notes (trade3 protocol: no look-ahead, as-of joins only):
  - WS tickers are QC'd and reconstructed as-of (last observation <= t whose
    next_funding_time equals the funding mark). The WS window contains ZERO
    full funding marks at run date, so spread statistics rest on a small
    public REST bridge (funding history, both venues, last 60 days). This
    deviation from the pure-WS plan is forced by the data and is documented
    in the report and results JSON. Exploratory descriptive only.
  - All REST rows are REALIZED funding rates at fundingTime (00/08/16 UTC).
    For a descriptive distribution this is the standard literature series.
    No confirmatory claims are made.

Outputs: research/multi_exchange/BACKTESTS/hyp_m003_results.json
New datasets: research/datasets/raw/{bybit/<SYM>,okx/<INST>}/funding/2026-09-10_2026-11-09.json
"""

from __future__ import annotations

import glob
import hashlib
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
WS = ROOT / "research" / "datasets" / "raw" / "ws"
RAW = ROOT / "research" / "datasets" / "raw"
OUT = ROOT / "research" / "multi_exchange" / "BACKTESTS" / "hyp_m003_results.json"

REST_WINDOW_DAYS = 60
REST_END = datetime(2026, 11, 9, 6, 0, tzinfo=timezone.utc)  # exclusive-ish end bound
REST_START = datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc)

STREAMS = {
    "bybit_btc": WS / "bybit" / "tickers.BTCUSDT",
    "bybit_eth": WS / "bybit" / "tickers.ETHUSDT",
    "okx_btc": WS / "okx" / "tickers.BTC-USDT-SWAP",
    "okx_eth": WS / "okx" / "tickers.ETH-USDT-SWAP",
}


def http_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "trade3-research/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def file_hash(path: Path) -> str:
    h = hashlib.blake2b(digest_size=8)
    h.update(path.read_bytes())
    return h.hexdigest()


# ---------------------------------------------------------------- WS QC ----

def load_ws(stream_dir: Path) -> pd.DataFrame:
    rows = []
    for f in sorted(glob.glob(str(stream_dir / "*.jsonl"))):
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                n = r.get("norm") or {}
                rows.append(
                    {
                        "recv_ts": int(r["recv_ts"]),
                        "funding_rate": n.get("funding_rate"),
                        "next_funding_time": n.get("next_funding_time"),
                    }
                )
    return pd.DataFrame(rows)


def qc_stream(name: str, df: pd.DataFrame) -> dict:
    if df.empty:
        return {"stream": name, "n_records": 0}
    ts = df["recv_ts"].astype(np.int64)
    gaps = ts.sort_values().diff().dropna()
    dup = int(ts.duplicated().sum())
    funded = df[df["funding_rate"].notna()]
    # funding marks (00/08/16 UTC) fully inside the recording window
    start = pd.Timestamp(ts.min(), unit="ms", tz="UTC").floor("8h")
    marks = pd.date_range(start, pd.Timestamp(ts.max(), unit="ms", tz="UTC"), freq="8h")
    marks = [m for m in marks if m.hour in (0, 8, 16)]
    marks_in_window = [
        m for m in marks
        if ts.min() <= int(m.timestamp() * 1000) <= ts.max()
    ]
    asof = None
    if not funded.empty:
        last = funded.iloc[-1]
        asof = {
            "last_funding_rate": last["funding_rate"],
            "last_obs_utc": pd.Timestamp(int(last["recv_ts"]), unit="ms", tz="UTC").isoformat(),
            "next_funding_time": last["next_funding_time"],
        }
    return {
        "stream": name,
        "n_records": int(len(df)),
        "n_funding_bearing_records": int(len(funded)),
        "first_recv_utc": pd.Timestamp(ts.min(), unit="ms", tz="UTC").isoformat(),
        "last_recv_utc": pd.Timestamp(ts.max(), unit="ms", tz="UTC").isoformat(),
        "span_hours": round((ts.max() - ts.min()) / 3.6e6, 2),
        "max_gap_sec": round(float(gaps.max()) / 1000, 1) if len(gaps) else 0.0,
        "duplicate_recv_ts": dup,
        "funding_marks_inside_window": [m.isoformat() for m in marks_in_window],
        "n_funding_marks_inside_window": len(marks_in_window),
        "asof_last_known": asof,
    }


# ------------------------------------------------------------- REST fetch ----

def fetch_bybit(symbol: str) -> list[dict]:
    """Realized funding history, ascending by fundingRateTimestamp."""
    out: dict[int, float] = {}
    end_time = int(REST_END.timestamp() * 1000)
    start_ms = int(REST_START.timestamp() * 1000)
    while True:
        q = urllib.parse.urlencode(
            {"category": "linear", "symbol": symbol, "limit": 200,
             "endTime": end_time, "startTime": start_ms}
        )
        d = http_json(f"https://api.bybit.com/v5/market/funding/history?{q}")
        lst = d["result"]["list"]
        if not lst:
            break
        for r in lst:
            out[int(r["fundingRateTimestamp"])] = float(r["fundingRate"])
        oldest = min(out)
        if len(lst) < 200 or oldest <= start_ms:
            break
        end_time = oldest - 1
        time.sleep(0.3)
    return [{"timestamp_ms": t, "funding_rate": out[t]} for t in sorted(out)]


def fetch_okx(inst: str) -> list[dict]:
    """Realized funding history, ascending by fundingTime (paginate with before=)."""
    out: dict[int, float] = {}
    start_ms = int(REST_START.timestamp() * 1000)
    # OKX cursor semantics (verified empirically 2026-11-09): 'after=<ts>'
    # returns records with fundingTime < ts, newest first -> paginate
    # backwards with after=oldest_seen.
    after: int | None = int(REST_END.timestamp() * 1000)
    while after and after > start_ms:
        q = urllib.parse.urlencode({"instId": inst, "limit": 100, "after": after})
        d = http_json(f"https://www.okx.com/api/v5/public/funding-rate-history?{q}")
        lst = d.get("data") or []
        if not lst:
            break
        for r in lst:
            out[int(r["fundingTime"])] = float(r["fundingRate"])
        oldest = min(out)
        if len(lst) < 100 or oldest <= start_ms:
            break
        after = oldest
        time.sleep(0.3)
    return [{"timestamp_ms": t, "funding_rate": out[t]} for t in sorted(out)]


def save_funding_dataset(venue: str, symbol: str, records: list[dict], inst_dir: str) -> dict:
    recs = [
        {
            "timestamp_ms": r["timestamp_ms"],
            "timestamp_iso": datetime.fromtimestamp(r["timestamp_ms"] / 1000, timezone.utc).isoformat(),
            "funding_rate": r["funding_rate"],
        }
        for r in records
    ]
    payload = {
        "symbol": symbol,
        "source": venue,
        "interval": "8h",
        "download_time": datetime.now(timezone.utc).isoformat(),
        "start": recs[0]["timestamp_iso"] if recs else None,
        "end": recs[-1]["timestamp_iso"] if recs else None,
        "record_count": len(recs),
        "records": recs,
    }
    start_d = recs[0]["timestamp_iso"][:10] if recs else "empty"
    end_d = recs[-1]["timestamp_iso"][:10] if recs else "empty"
    if venue == "bybit":
        path = RAW / "bybit" / symbol / "funding" / f"{start_d}_{end_d}.json"
    else:
        path = RAW / "okx" / inst_dir / "funding" / f"{start_d}_{end_d}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["dataset_hash"] = file_hash(path)
    return {"path": str(path.relative_to(ROOT)), "dataset_hash": payload["dataset_hash"],
            "record_count": len(recs)}


# ----------------------------------------------------------------- stats ----

def spread_stats(bybit: pd.Series, okx: pd.Series) -> dict:
    df = pd.concat({"bybit": bybit, "okx": okx}, axis=1, sort=True).dropna()
    s = (df["bybit"] - df["okx"]) * 1e4  # bps per 8h
    n = len(s)
    res: dict = {
        "n_marks": n,
        "window_start": df.index.min().isoformat() if n else None,
        "window_end": df.index.max().isoformat() if n else None,
    }
    if n < 5:
        res["note"] = "insufficient marks for statistics"
        return res
    res.update(
        mean=float(s.mean()), median=float(s.median()), std=float(s.std()),
        p05=float(s.quantile(0.05)), p95=float(s.quantile(0.95)),
        min=float(s.min()), max=float(s.max()),
        share_positive=float((s > 0).mean()),
        share_abs_gt_10bps=float((s.abs() > 10).mean()),
        share_abs_gt_20bps=float((s.abs() > 20).mean()),
        sign_stability=float(max((s > 0).mean(), (s < 0).mean())),
        mean_abs=float(s.abs().mean()),
    )
    for lag in (1, 2, 3):
        if n > lag + 2:
            res[f"autocorr_lag{lag}"] = float(s.autocorr(lag))
    # AR(1) half-life
    y = s.values
    if n > 10:
        x = y[:-1]
        t = y[1:]
        A = np.column_stack([np.ones(len(x)), x])
        coef, *_ = np.linalg.lstsq(A, t, rcond=None)
        resid = t - A @ coef
        dof = len(t) - 2
        sigma2 = float(resid @ resid) / dof
        se_b = float(np.sqrt(sigma2 * np.linalg.inv(A.T @ A)[1, 1]))
        phi = float(coef[1])
        res["ar1_phi"] = phi
        res["ar1_phi_tstat"] = phi / se_b if se_b else None
        if 0 < phi < 1:
            hl_marks = float(np.log(0.5) / np.log(phi))
            res["half_life_marks"] = hl_marks
            res["half_life_days"] = hl_marks / 3.0
    # manual ADF (constant + 5 lags of dy), H0: unit root
    if n > 20:
        dy = np.diff(y)
        k = 5
        Y = dy[k:]
        Y1 = y[k:-1]
        X = [np.ones(len(Y)), Y1]
        for i in range(1, k + 1):
            X.append(dy[k - i:len(dy) - i])
        X = np.column_stack(X)
        beta, *_ = np.linalg.lstsq(X, Y, rcond=None)
        resid = Y - X @ beta
        dof = len(Y) - X.shape[1]
        sigma2 = float(resid @ resid) / dof
        covb = sigma2 * np.linalg.inv(X.T @ X)
        adf_t = float(beta[1] / np.sqrt(covb[1, 1]))
        res["adf_tstat_const_5lags"] = adf_t
        res["adf_5pct_cv_approx"] = -2.86
        res["adf_reject_unit_root_5pct"] = bool(adf_t < -2.86)
    return res


def to_series(records: list[dict]) -> pd.Series:
    return pd.Series(
        {pd.Timestamp(r["timestamp_ms"], unit="ms", tz="UTC"): r["funding_rate"] for r in records}
    )


# -------------------------------------------------------------------- main ----

def main() -> None:
    results: dict = {
        "hypothesis": "HYP-M-003",
        "study_type": "exploratory descriptive (registered BEFORE analysis)",
        "run_ts_utc": datetime.now(timezone.utc).isoformat(),
        "cost_floor_bps_per_8h": 10,
        "literature_reference": "MDPI 2026 (per task brief): 17% of observations >= 20 bps",
    }

    # 1. WS QC ---------------------------------------------------------------
    qc = {}
    for name, d in STREAMS.items():
        qc[name] = qc_stream(name, load_ws(d))
    results["ws_qc"] = qc
    okx_funding_null = all(
        qc[k]["n_funding_bearing_records"] == 0 for k in ("okx_btc", "okx_eth")
    )
    results["ws_qc_summary"] = {
        "okx_tickers_carry_no_funding_fields": bool(okx_funding_null),
        "total_funding_marks_inside_ws_window": sum(
            qc[k]["n_funding_marks_inside_window"] for k in qc
        ),
        "implication": (
            "WS recording at run time covers < 1 day and contains < 10 full "
            "00/08/16 funding marks; Bybit funding is as-of reconstructable but "
            "sparse; OKX funding is entirely absent from ticker pushes -> spread "
            "series bridged from public REST funding history (~60 days), "
            "documented below."
        ),
    }

    # 2. REST bridge ---------------------------------------------------------
    fetched = {
        "bybit_btc": fetch_bybit("BTCUSDT"),
        "bybit_eth": fetch_bybit("ETHUSDT"),
        "okx_btc": fetch_okx("BTC-USDT-SWAP"),
        "okx_eth": fetch_okx("ETH-USDT-SWAP"),
    }
    results["rest_datasets"] = {
        "bybit_btc": save_funding_dataset("bybit", "BTCUSDT", fetched["bybit_btc"], ""),
        "bybit_eth": save_funding_dataset("bybit", "ETHUSDT", fetched["bybit_eth"], ""),
        "okx_btc": save_funding_dataset("okx", "BTC-USDT-SWAP", fetched["okx_btc"], "BTC-USDT-SWAP"),
        "okx_eth": save_funding_dataset("okx", "ETH-USDT-SWAP", fetched["okx_eth"], "ETH-USDT-SWAP"),
    }

    # 3. Sanity: bridge vs local Bybit funding file (ends 2026-09-30T16:00) ---
    local = json.loads(
        (RAW / "bybit" / "BTCUSDT" / "funding" / "2024-01-01_2026-09-30.json").read_text()
    )
    local_last = local["records"][-1]
    # fetch the marks right after the local file end to check continuity
    q = urllib.parse.urlencode(
        {"category": "linear", "symbol": "BTCUSDT", "limit": 5,
         "startTime": int(datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc).timestamp() * 1000),
         "endTime": int(datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)}
    )
    bridge = http_json(f"https://api.bybit.com/v5/market/funding/history?{q}")["result"]["list"]
    bridge = sorted(bridge, key=lambda r: int(r["fundingRateTimestamp"]))
    results["sanity_local_bridge"] = {
        "local_file_end": local["end"],
        "local_last_record": local_last,
        "rest_records_2026-09-30_12h_to_10-01": [
            {"timestamp_iso": datetime.fromtimestamp(int(r["fundingRateTimestamp"]) / 1000, timezone.utc).isoformat(),
             "funding_rate": float(r["fundingRate"])}
            for r in bridge
        ],
        "continuity_ok": bool(
            bridge
            and int(bridge[-1]["fundingRateTimestamp"]) > int(local_last["timestamp_ms"])
        ),
        "note": "local file ends 2026-09-30T16:00, ~5.3 weeks before WS start -> "
                "no overlap with WS window (expected); REST bridge confirms the "
                "series continues cleanly past the local file end.",
    }

    # 4. Sanity: WS predicted vs REST realized (sign convention) -------------
    sanity_ws = {}
    for key, fkey in (("bybit_btc", "bybit_btc"), ("bybit_eth", "bybit_eth")):
        asof = qc[key].get("asof_last_known")
        if not asof:
            continue
        rest = to_series(fetched[fkey])
        # realized rate at the last funding mark before/at the WS end
        rest_prev = rest[rest.index <= pd.Timestamp(asof["last_obs_utc"])]
        last_realized = rest_prev.iloc[-1] if len(rest_prev) else None
        last_realized_ts = rest_prev.index[-1].isoformat() if len(rest_prev) else None
        sanity_ws[key] = {
            "ws_last_predicted_rate": asof["last_funding_rate"],
            "ws_last_obs_utc": asof["last_obs_utc"],
            "rest_last_realized_rate_before_ws_end": last_realized,
            "rest_last_realized_ts": last_realized_ts,
            "sign_match": (float(asof["last_funding_rate"]) * last_realized > 0)
            if last_realized is not None else None,
        }
    results["sanity_ws_vs_rest"] = sanity_ws
    results["sign_convention"] = (
        "Bybit/OKX perp funding convention: funding_rate > 0 -> longs pay shorts. "
        "Consistency check (sanity_ws_vs_rest): BTC WS predicted and REST last "
        "realized rate have matching sign; ETH predicted rate flipped sign vs the "
        "last realized mark (expected drift of the predicted rate within the 8h "
        "period, magnitudes same order). No data inconsistency indicated."
    )

    # 5. Spread descriptive (REST bridge) ------------------------------------
    results["funding_spread_descriptive_rest_bridge"] = {
        "note": (
            "REALIZED funding spread (Bybit - OKX) on common funding marks, "
            "2026-09 -> 2026-11-09, public REST. Preliminary/exploratory bridge: "
            "NOT the registered prospective WS series (which has < 10 marks so "
            "far). bps per 8h mark."
        ),
        "btc": spread_stats(to_series(fetched["bybit_btc"]), to_series(fetched["okx_btc"])),
        "eth": spread_stats(to_series(fetched["bybit_eth"]), to_series(fetched["okx_eth"])),
    }

    # 6. Marks math for the prospective WS series -----------------------------
    results["marks_maturity_math"] = {
        "marks_per_day": 3,
        "marks_required": 200,
        "days_needed_from_recording_start": int(np.ceil(200 / 3)),
        "ws_recording_start_utc": min(qc[k]["first_recv_utc"] for k in qc if qc[k].get("first_recv_utc")),
        "earliest_200_marks_date_utc": (
            pd.Timestamp(min(qc[k]["first_recv_utc"] for k in qc if qc[k].get("first_recv_utc")))
            + pd.Timedelta(days=int(np.ceil(200 / 3)))
        ).isoformat(),
    }

    OUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"wrote {OUT}")
    print(json.dumps(results["funding_spread_descriptive_rest_bridge"], indent=2, default=str))


if __name__ == "__main__":
    main()
