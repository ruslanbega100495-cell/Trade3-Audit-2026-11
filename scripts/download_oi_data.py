"""
Download BTCUSDT H4 Open Interest history from Bybit.

Saves to: research/datasets/raw/bybit/BTCUSDT/H4/oi_2024-01-01_2026-09-30.json

Format per record:
  { "timestamp_ms": int, "open_interest": float }

timestamp_ms is the START of the 4h interval (matches candle open_time).

Bybit API: /v5/market/open-interest
  - category: linear
  - intervalTime: 4h
  - limit: 200 per page
  - Paginates backwards via cursor
"""
from __future__ import annotations
import json
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from pybit.unified_trading import HTTP
except ImportError:
    raise SystemExit("pybit not installed: pip install pybit")

SYMBOL = "BTCUSDT"
INTERVAL = "4h"
START_DT = datetime(2024, 1, 1, tzinfo=timezone.utc)
END_DT   = datetime(2026, 10, 1, tzinfo=timezone.utc)
LIMIT    = 200
OUT_DIR  = Path(__file__).parent.parent / "research" / "datasets" / "raw" / "bybit" / SYMBOL / "H4"

START_MS = int(START_DT.timestamp() * 1000)
END_MS   = int(END_DT.timestamp() * 1000)


def fetch_all_oi() -> list[dict]:
    session = HTTP(testnet=False)
    records: list[dict] = []
    cursor = None
    page = 0

    while True:
        kwargs: dict = dict(
            category="linear",
            symbol=SYMBOL,
            intervalTime=INTERVAL,
            limit=LIMIT,
            startTime=START_MS,
            endTime=END_MS,
        )
        if cursor:
            kwargs["cursor"] = cursor

        resp = session.get_open_interest(**kwargs)
        if resp["retCode"] != 0:
            raise RuntimeError(f"Bybit error {resp['retCode']}: {resp['retMsg']}")

        batch = resp["result"]["list"]
        cursor = resp["result"].get("nextPageCursor", "") or ""

        for item in batch:
            ts = int(item["timestamp"])
            oi = float(item["openInterest"])
            if START_MS <= ts < END_MS:
                records.append({"timestamp_ms": ts, "open_interest": oi})

        page += 1
        print(f"  Page {page}: {len(batch)} items, cursor={bool(cursor)}")

        if not cursor or not batch:
            break
        time.sleep(0.15)  # respect rate limits

    # deduplicate and sort ascending
    seen: dict[int, float] = {}
    for r in records:
        seen[r["timestamp_ms"]] = r["open_interest"]
    sorted_records = [
        {"timestamp_ms": k, "open_interest": v}
        for k, v in sorted(seen.items())
    ]
    return sorted_records


def main() -> None:
    print(f"Downloading BTCUSDT H4 OI: {START_DT.date()} → {END_DT.date()}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "oi_2024-01-01_2026-09-30.json"

    records = fetch_all_oi()
    print(f"Total records: {len(records)}")

    if records:
        first_ts = datetime.fromtimestamp(records[0]["timestamp_ms"] / 1000, tz=timezone.utc)
        last_ts  = datetime.fromtimestamp(records[-1]["timestamp_ms"] / 1000, tz=timezone.utc)
        print(f"Range: {first_ts} → {last_ts}")

    payload = {
        "symbol":       SYMBOL,
        "interval":     INTERVAL,
        "start":        START_DT.isoformat(),
        "end":          END_DT.isoformat(),
        "total_records": len(records),
        "records":      records,
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Saved → {out_path}")


if __name__ == "__main__":
    main()
