"""
One-time data collection script for Bybit public market data.
Usage:
  python research/scripts/collect_bybit.py klines --symbol ETHUSDT --category linear --start 2024-01-01 --end 2026-09-30 --out research/datasets/raw/bybit/ETHUSDT/H4/2024-01-01_2026-09-30.json
  python research/scripts/collect_bybit.py funding --symbol BTCUSDT --start 2024-01-01 --end 2026-09-30 --out research/datasets/raw/bybit/BTCUSDT/funding/2024-01-01_2026-09-30.json
"""
import argparse, hashlib, json, os, time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_URL = "https://api.bybit.com"
SLEEP_BETWEEN = 0.25  # seconds between requests — respect rate limits

def dt_to_ms(date_str: str) -> int:
    """YYYY-MM-DD → Unix ms UTC."""
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)

def ms_to_iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()

def compute_hash(candles: list) -> str:
    payload = json.dumps([(c["open_time"], c["close"]) for c in candles], separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]

def download_klines(symbol: str, category: str, start_ms: int, end_ms: int) -> list:
    """Download all H4 OHLCV candles for the given period via Bybit V5 API."""
    candles = []
    url = f"{BASE_URL}/v5/market/kline"
    batch_start = start_ms
    interval = 240  # H4 = 240 minutes
    batch_size_ms = 200 * interval * 60 * 1000  # 200 candles per request

    while batch_start < end_ms:
        batch_end = min(batch_start + batch_size_ms, end_ms)
        params = {
            "category": category,
            "symbol": symbol,
            "interval": str(interval),
            "start": str(batch_start),
            "end": str(batch_end),
            "limit": 200,
        }
        # Retry on transient server errors
        for attempt in range(3):
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if data.get("retCode") == 0:
                break
            if attempt < 2:
                print(f"  Retrying (attempt {attempt+1}/3) after API error: {data.get('retMsg')}")
                time.sleep(2)
            else:
                raise ValueError(f"Bybit API error after retries: {data}")
        items = data["result"]["list"]
        if not items:
            batch_start = batch_end
            time.sleep(SLEEP_BETWEEN)
            continue
        # Bybit returns newest-first; reverse each batch
        for item in reversed(items):
            ts_ms = int(item[0])
            if ts_ms < end_ms:  # exclude future partial candles
                candles.append({
                    "open_time": ms_to_iso(ts_ms),
                    "open": item[1],
                    "high": item[2],
                    "low": item[3],
                    "close": item[4],
                    "volume": item[5],
                    "turnover": item[6],
                })
        # Advance to end of last fetched candle + 1 interval
        last_ts = int(items[0][0])  # items[0] = newest (Bybit returns newest-first)
        batch_start = last_ts + interval * 60 * 1000
        time.sleep(SLEEP_BETWEEN)

    # Deduplicate by open_time and sort
    seen = {}
    for c in candles:
        seen[c["open_time"]] = c
    candles = sorted(seen.values(), key=lambda c: c["open_time"])
    return candles

def download_funding(symbol: str, start_ms: int, end_ms: int) -> list:
    """Download all historical funding rate records for the given period.

    Uses explicit startTime/endTime with 30-day sliding windows to reliably
    retrieve full historical data from the Bybit V5 funding history endpoint.
    """
    records = []
    url = f"{BASE_URL}/v5/market/funding/history"
    CHUNK_MS = 30 * 24 * 3600 * 1000  # 30-day chunks

    chunk_start = start_ms
    while chunk_start < end_ms:
        chunk_end = min(chunk_start + CHUNK_MS, end_ms)
        cursor = None
        while True:
            params = {
                "category": "linear",
                "symbol": symbol,
                "limit": 200,
                "startTime": str(chunk_start),
                "endTime": str(chunk_end),
            }
            if cursor:
                params["cursor"] = cursor
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if data.get("retCode") != 0:
                raise ValueError(f"Bybit API error: {data}")
            items = data["result"]["list"]
            if not items:
                break
            for item in items:
                ts_ms = int(item["fundingRateTimestamp"])
                if start_ms <= ts_ms < end_ms:
                    records.append({
                        "timestamp_ms": ts_ms,
                        "timestamp_iso": ms_to_iso(ts_ms),
                        "funding_rate": float(item["fundingRate"]),
                    })
            cursor = data["result"].get("nextPageCursor")
            if not cursor:
                break
            time.sleep(SLEEP_BETWEEN)
        chunk_start = chunk_end
        time.sleep(SLEEP_BETWEEN)

    # Deduplicate and sort
    seen = {}
    for r in records:
        seen[r["timestamp_ms"]] = r
    records = sorted(seen.values(), key=lambda r: r["timestamp_ms"])
    return [r for r in records if start_ms <= r["timestamp_ms"] < end_ms]

def save_klines(symbol: str, category: str, candles: list, out_path: str):
    if not candles:
        raise ValueError("No candles to save")
    dataset_hash = compute_hash(candles)
    out = {
        "symbol": symbol,
        "category": category,
        "timeframe": "H4",
        "source": "bybit",
        "download_time": datetime.now(timezone.utc).isoformat(),
        "start": candles[0]["open_time"],
        "end": candles[-1]["open_time"],
        "record_count": len(candles),
        "dataset_hash": dataset_hash,
        "candles": candles,
    }
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(candles)} candles to {out_path} (hash={dataset_hash})")
    return dataset_hash

def save_funding(symbol: str, records: list, out_path: str):
    if not records:
        raise ValueError("No funding records to save")
    payload = json.dumps([(r["timestamp_ms"], r["funding_rate"]) for r in records], separators=(",", ":"))
    dataset_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]
    out = {
        "symbol": symbol,
        "source": "bybit",
        "interval": "8h",
        "download_time": datetime.now(timezone.utc).isoformat(),
        "start": records[0]["timestamp_iso"],
        "end": records[-1]["timestamp_iso"],
        "record_count": len(records),
        "dataset_hash": dataset_hash,
        "records": records,
    }
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(records)} funding records to {out_path} (hash={dataset_hash})")
    return dataset_hash

def qc_klines(candles: list, symbol: str) -> bool:
    """Basic QC checks."""
    if not candles:
        print(f"QC FAIL {symbol}: empty"); return False
    times = [c["open_time"] for c in candles]
    if times != sorted(times):
        print(f"QC FAIL {symbol}: timestamps not sorted"); return False
    if len(times) != len(set(times)):
        print(f"QC FAIL {symbol}: duplicate timestamps"); return False
    # Check for gaps (should be exactly 4h between consecutive candles)
    from datetime import datetime, timezone
    import math
    diffs = []
    for i in range(1, len(candles)):
        t1 = datetime.fromisoformat(candles[i-1]["open_time"].replace("+00:00", "+00:00"))
        t2 = datetime.fromisoformat(candles[i]["open_time"].replace("+00:00", "+00:00"))
        diff_h = (t2 - t1).total_seconds() / 3600
        if diff_h > 8:  # more than 2 missing H4 candles
            diffs.append((candles[i-1]["open_time"], diff_h))
    if diffs:
        print(f"QC WARN {symbol}: {len(diffs)} gaps > 8h found: {diffs[:3]}")
    print(f"QC OK {symbol}: {len(candles)} candles, {times[0]} to {times[-1]}")
    return True

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")

    k = sub.add_parser("klines")
    k.add_argument("--symbol", required=True)
    k.add_argument("--category", default="linear")
    k.add_argument("--start", required=True)
    k.add_argument("--end", required=True)
    k.add_argument("--out", required=True)

    f = sub.add_parser("funding")
    f.add_argument("--symbol", required=True)
    f.add_argument("--start", required=True)
    f.add_argument("--end", required=True)
    f.add_argument("--out", required=True)

    args = parser.parse_args()

    if args.cmd == "klines":
        start_ms = dt_to_ms(args.start)
        end_ms = dt_to_ms(args.end) + 24*3600*1000  # include end date
        print(f"Downloading {args.symbol} {args.category} H4 klines {args.start} to {args.end}...")
        candles = download_klines(args.symbol, args.category, start_ms, end_ms)
        qc_klines(candles, args.symbol)
        save_klines(args.symbol, args.category, candles, args.out)
    elif args.cmd == "funding":
        start_ms = dt_to_ms(args.start)
        end_ms = dt_to_ms(args.end) + 24*3600*1000
        print(f"Downloading {args.symbol} funding history {args.start} to {args.end}...")
        records = download_funding(args.symbol, start_ms, end_ms)
        save_funding(args.symbol, records, args.out)

if __name__ == "__main__":
    main()
