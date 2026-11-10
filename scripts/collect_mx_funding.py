"""Сборщик funding-историй KuCoin и HTX для HYP-M-005.

Формат выхода совместим с Bybit funding-файлами:
{funding: [{timestamp (ISO UTC), funding_rate}, ...], dataset_hash, ...}

Usage: .venv/Scripts/python.exe -X utf8 scripts/collect_mx_funding.py
"""
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

H = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
S = requests.Session()
S.headers.update(H)
OUT = Path("research/datasets/raw")
START_MS = 1704067200000   # 2024-01-01 (окно TRAIN M-005; история глубже не нужна)


def iso(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat()


def get(url, params, venue, pause=1.5):
    for attempt in range(5):
        try:
            r = S.get(url, params=params, timeout=20)
            if r.status_code == 200:
                time.sleep(pause)
                return r.json()
            time.sleep(2 * (attempt + 1))
        except requests.RequestException:
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{venue} failed after retries: {url}")


def fetch_kucoin():
    url = "https://api-futures.kucoin.com/api/v1/contract/funding-rates"
    win = 30 * 24 * 3600 * 1000  # 30 дней за запрос
    recs, cursor = {}, START_MS
    end = int(time.time() * 1000)
    while cursor < end:
        to = min(cursor + win, end)
        j = get(url, {"symbol": "XBTUSDTM", "from": cursor, "to": to}, "kucoin", pause=0.7)
        for d in j.get("data", []):
            recs[int(d["timepoint"])] = float(d["fundingRate"])
        cursor = to
    return recs


def fetch_htx():
    url = "https://api.hbdm.com/linear-swap-api/v1/swap_historical_funding_rate"
    recs = {}
    page = 1
    total = None
    while True:
        j = get(url, {"contract_code": "BTC-USDT", "page_index": page, "page_size": 50},
                "htx", pause=1.2)
        data = j.get("data", {})
        if total is None:
            total = int(data.get("total_page", 1))
        rows = data.get("data", [])
        if not rows:
            break
        for d in rows:
            ts = int(d["funding_time"])
            if ts >= START_MS:
                recs[ts] = float(d["funding_rate"])
        if page >= total:
            break
        page += 1
        if page % 20 == 0:
            print(f"  htx page {page}/{total}, recs {len(recs)}")
    return recs


def save(venue, recs):
    rows = [{"timestamp": iso(ts), "funding_rate": recs[ts]} for ts in sorted(recs)]
    payload = json.dumps([(r["timestamp"], r["funding_rate"]) for r in rows],
                         separators=(",", ":"))
    h = hashlib.sha256(payload.encode()).hexdigest()[:16]
    out = {
        "symbol": "BTCUSDT", "type": "funding_history", "source": venue,
        "download_time": iso(int(time.time() * 1000)),
        "start": rows[0]["timestamp"], "end": rows[-1]["timestamp"],
        "record_count": len(rows), "dataset_hash": h, "funding": rows,
    }
    d0, d1 = rows[0]["timestamp"][:10], rows[-1]["timestamp"][:10]
    path = OUT / venue / "BTCUSDT" / "funding" / f"{d0}_{d1}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(path, "w"), indent=2)
    print(f"{venue}: {len(rows)} records -> {path} (hash={h})")


if __name__ == "__main__":
    print("=== kucoin")
    save("kucoin", fetch_kucoin())
    print("=== htx")
    save("htx", fetch_htx())
