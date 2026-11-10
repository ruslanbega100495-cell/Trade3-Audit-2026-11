"""Сборщик 1h BTCUSDT klines с шести бирж для HYP-M-001 (cross-exchange dislocation).

Venues: bybit, okx, kucoin, htx, weex, bingx. Публичные API, без ключей.

Формат выходного файла — как research/datasets/raw/bybit/BTCUSDT/H4/*.json:
  {symbol, timeframe, source, download_time, start, end, record_count, dataset_hash, candles}
candles: [{open_time (ISO UTC), open, high, low, close, volume, turnover}, ...] — цены строками.

dataset_hash: sha256 от json.dumps([(open_time, close), ...], separators=(",", ":"))[:16]
(тот же метод, что в research/scripts/collect_bybit.py).

Нормализация volume — в базовый актив (BTC):
  bybit: vol (BTC) | okx: volCcy (BTC) | kucoin: contracts*0.001 | htx: amount (BTC)
  weex: vol (BTC) | bingx: volume (BTC)

Rate limits: >=1.5s между запросами одной биржи, >=0.5s между любыми запросами;
retry с exponential backoff при 429/5xx/таймаутах (макс 5 попыток).

Usage: .venv/Scripts/python.exe scripts/collect_mx_klines.py [--venue all|bybit|...]
"""
import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

START_MS = 1711929600000          # 2024-04-01T00:00:00Z
HOUR = 3600_000
# END: последний ЗАКРЫТЫй часовой бар на момент запуска (не захватываем бар в прогрессе).
END_MS = int(time.time() * 1000) // HOUR * HOUR
OUT_ROOT = Path("research/datasets/raw")

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)

_last_request = {"t": 0.0}
_last_venue = {"v": None, "t": 0.0}


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}", flush=True)


def throttled_get(venue: str, url: str, params: dict) -> requests.Response:
    """GET с rate-limit паузами и retry/backoff на 429/5xx/сетевых ошибках."""
    for attempt in range(5):
        now = time.monotonic()
        wait = 0.5 - (now - _last_request["t"])                       # глобальный зазор
        if _last_venue["v"] == venue:
            wait = max(wait, 1.5 - (now - _last_venue["t"]))          # зазор внутри биржи
        if wait > 0:
            time.sleep(wait)
        _last_request["t"] = time.monotonic()
        _last_venue["v"] = venue
        _last_venue["t"] = _last_request["t"]
        try:
            r = SESSION.get(url, params=params, timeout=30)
        except requests.RequestException as e:
            log(f"  {venue}: network error {e!r} (attempt {attempt + 1}/5)")
            time.sleep(1.5 * (2 ** attempt))
            continue
        if r.status_code in (429, 500, 502, 503, 504):
            log(f"  {venue}: HTTP {r.status_code} (attempt {attempt + 1}/5), backoff")
            time.sleep(1.5 * (2 ** attempt) + 1.0)
            continue
        r.raise_for_status()
        return r
    raise RuntimeError(f"{venue}: failed after 5 attempts: {url}")


def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def candle(ts_ms: int, o, h, l, c, vol, turnover=None) -> dict:
    d = {
        "open_time": iso(ts_ms),
        "open": str(o), "high": str(h), "low": str(l), "close": str(c),
        "volume": str(vol),
    }
    if turnover is not None:
        d["turnover"] = str(turnover)
    return d


# --------------------------------------------------------------------------- bybit
def fetch_bybit() -> list:
    # Bybit отдаёт NEWEST-first в окне [start, end]: пагинируем НАЗАД от END_MS.
    url = "https://api.bybit.com/v5/market/kline"
    pages, cursor = [], END_MS
    while cursor > START_MS:
        r = throttled_get("bybit", url, dict(
            category="linear", symbol="BTCUSDT", interval="60",
            start=str(START_MS), end=str(cursor - 1), limit="1000"))
        data = r.json().get("result", {}).get("list", [])
        bars = [b for b in data if START_MS <= int(b[0]) < cursor]
        if not bars:
            break
        pages.extend(bars)
        cursor = min(int(b[0]) for b in bars)
        log(f"  bybit: {len(pages)} bars, cursor {iso(cursor)}")
    candles = []
    seen = set()
    for b in pages:
        ts = int(b[0])
        if ts in seen:
            continue
        seen.add(ts)
        candles.append(candle(ts, b[1], b[2], b[3], b[4], b[5], b[6]))
    candles.sort(key=lambda c: c["open_time"])
    return candles


# --------------------------------------------------------------------------- okx
def fetch_okx() -> list:
    url = "https://openapi.okx.com/api/v5/market/history-candles"
    pages, after = [], END_MS - 1          # якорь: первая страница — бары СТАРШЕ END
    while True:
        params = dict(instId="BTC-USDT-SWAP", bar="1H", limit="100", after=str(after))
        r = throttled_get("okx", url, params)
        data = [row for row in r.json().get("data", []) if int(row[0]) < after]
        if not data:
            break
        pages.extend(data)
        after = min(int(row[0]) for row in data)
        log(f"  okx: {len(pages)} bars, cursor {iso(after)}")
        if after <= START_MS:
            break
    candles = []
    seen = set()
    for row in pages:
        ts = int(row[0])
        if ts < START_MS or ts >= END_MS or ts in seen:
            continue
        seen.add(ts)
        candles.append(candle(ts, row[1], row[2], row[3], row[4], row[6], row[7]))
    candles.sort(key=lambda c: c["open_time"])
    return candles


# --------------------------------------------------------------------------- kucoin
def fetch_kucoin() -> list:
    url = "https://api-futures.kucoin.com/api/v1/kline/query"
    win = 200 * HOUR                     # API отдаёт макс 200 баров; окно = 200 часов
    candles, seen, frm = [], set(), START_MS
    while frm < END_MS:
        to = min(frm + win, END_MS) - 1
        r = throttled_get("kucoin", url, dict(
            symbol="XBTUSDTM", granularity="60",
            **{"from": str(frm)}, **{"to": str(to)}))
        data = r.json().get("data", [])
        if data:
            first_ts, max_ts = int(data[0][0]), max(int(d[0]) for d in data)
            if len(data) == 200 and first_ts > frm:
                # усечение со стороны начала окна — сузить окно и повторить
                log(f"  kucoin: truncation at {iso(frm)}, shrinking window")
                continue
            for d in data:
                ts = int(d[0])
                if START_MS <= ts < END_MS and ts not in seen:
                    seen.add(ts)
                    candles.append(candle(ts, d[1], d[2], d[3], d[4],
                                          float(d[5]) * 0.001, d[6]))   # контракты 0.001 BTC
            frm = max_ts + HOUR
        else:
            frm += win
        log(f"  kucoin: {len(candles)} bars, cursor {iso(frm)}")
    candles.sort(key=lambda c: c["open_time"])
    return candles


# --------------------------------------------------------------------------- htx
def fetch_htx() -> list:
    # HTX при больших окнах обрезает выдачу (может игнорировать from/to и отдавать
    # newest-2000 до 'to') — пагинируем НАЗАД от END_MS с уменьшением окна при truncation.
    url = "https://api.hbdm.com/linear-swap-ex/market/history/kline"
    candles, seen = [], set()
    cursor, win = END_MS, 2000 * HOUR
    while cursor > START_MS and win >= HOUR:
        frm = max(START_MS, cursor - win)
        r = throttled_get("htx", url, dict(
            contract_code="BTC-USDT", period="60min",
            **{"from": str(frm // 1000)}, **{"to": str((cursor - 1) // 1000)}, size="2000"))
        data = r.json().get("data", [])
        if not isinstance(data, list):
            data = data.get("items", []) if isinstance(data, dict) else []
        if not data:
            cursor = frm
            log(f"  htx: {len(candles)} bars, cursor {iso(cursor)} (empty)")
            continue
        ids = [int(d["id"]) for d in data]
        # truncation сверху: выдача не достигает cursor-1 — уменьшаем окно
        if len(data) == 2000 and (max(ids) + 1) * 1000 < cursor - HOUR:
            win //= 2
            log(f"  htx: truncation below cursor, win -> {win // HOUR}h")
            continue
        took = 0
        for d in data:
            ts = int(d["id"]) * 1000
            if START_MS <= ts < cursor and ts not in seen:
                seen.add(ts)
                candles.append(candle(ts, d["open"], d["high"], d["low"], d["close"],
                                      d["amount"], d.get("trade_turnover")))
                took += 1
        if took == 0:
            win //= 2
            if win < HOUR:
                break
            continue
        cursor = min(ids) * 1000
        log(f"  htx: {len(candles)} bars, cursor {iso(cursor)}")
    candles.sort(key=lambda c: c["open_time"])
    return candles


# --------------------------------------------------------------------------- weex
def fetch_weex() -> list:
    # WEEX historyKlines: НЕ принимает limit (400), ответ — голый JSON-список,
    # ровно 100 баров (newest-first) внутри [startTime, endTime]; окно = 99 часов,
    # усечения нет — API честно отдаёт хвост окна.
    url = "https://api-contract.weex.com/capi/v3/market/historyKlines"
    win = 99 * HOUR
    candles, seen, cursor = [], set(), START_MS
    while cursor < END_MS:
        end = min(cursor + win, END_MS) - 1
        r = throttled_get("weex", url, dict(
            symbol="BTCUSDT", interval="1h",
            startTime=str(cursor), endTime=str(end)))
        data = r.json()
        if isinstance(data, dict):
            data = data.get("data", [])
        if not data:
            cursor += win
            log(f"  weex: {len(candles)} bars, cursor {iso(cursor)} (empty)")
            continue
        tss = [int(d[0]) for d in data]
        for d in data:
            ts = int(d[0])
            if START_MS <= ts < END_MS and ts not in seen:
                seen.add(ts)
                candles.append(candle(ts, d[1], d[2], d[3], d[4], d[5], d[7]))
        cursor = max(tss) + HOUR
        log(f"  weex: {len(candles)} bars, cursor {iso(cursor)}")
    candles.sort(key=lambda c: c["open_time"])
    return candles


# --------------------------------------------------------------------------- bingx
def fetch_bingx() -> list:
    url = "https://open-api.bingx.com/openApi/swap/v2/quote/klines"
    win = 1000 * HOUR
    candles, seen, cursor = [], set(), START_MS
    while cursor < END_MS:
        end = min(cursor + win, END_MS) - 1
        r = throttled_get("bingx", url, dict(
            symbol="BTC-USDT", interval="1h",
            startTime=str(cursor), endTime=str(end), limit="1000"))
        data = r.json().get("data", [])
        if not data:
            cursor += win
            log(f"  bingx: {len(candles)} bars, cursor {iso(cursor)} (empty)")
            continue
        tss = [int(d["time"]) for d in data]
        if len(data) == 1000 and min(tss) > cursor:
            end = min(tss) - HOUR
        else:
            for d in data:
                ts = int(d["time"])
                if START_MS <= ts < END_MS and ts not in seen:
                    seen.add(ts)
                    candles.append(candle(ts, d["open"], d["high"], d["low"], d["close"],
                                          d["volume"]))
            cursor = max(tss) + HOUR
        log(f"  bingx: {len(candles)} bars, cursor {iso(cursor)}")
    candles.sort(key=lambda c: c["open_time"])
    return candles


VENUES = {
    "bybit": fetch_bybit,
    "okx": fetch_okx,
    "kucoin": fetch_kucoin,
    "htx": fetch_htx,
    "weex": fetch_weex,
    "bingx": fetch_bingx,
}


def qc(candles: list, venue: str) -> list:
    """Дедуп + монотонность + список гэпов > 2 баров. Пропуски не интерполируем."""
    seen, out, gaps = set(), [], []
    for c in candles:
        if c["open_time"] in seen:
            continue
        seen.add(c["open_time"])
        out.append(c)
    out.sort(key=lambda c: c["open_time"])
    for a, b in zip(out, out[1:]):
        ta = datetime.fromisoformat(a["open_time"]).timestamp()
        tb = datetime.fromisoformat(b["open_time"]).timestamp()
        if tb - ta > 2 * 3600:
            gaps.append((a["open_time"], b["open_time"]))
    if gaps:
        log(f"  {venue}: {len(gaps)} gaps > 2 bars")
        for g in gaps[:20]:
            log(f"    gap {g[0]} -> {g[1]}")
    return out


def save(venue: str, candles: list) -> Path | None:
    if not candles:
        log(f"{venue}: no data, file not written")
        return None
    payload = json.dumps([(c["open_time"], c["close"]) for c in candles],
                         separators=(",", ":"))
    h = hashlib.sha256(payload.encode()).hexdigest()[:16]
    d0 = candles[0]["open_time"][:10]
    d1 = candles[-1]["open_time"][:10]
    out = {
        "symbol": "BTCUSDT",
        "timeframe": "H1",
        "source": venue,
        "download_time": datetime.now(timezone.utc).isoformat(),
        "start": candles[0]["open_time"],
        "end": candles[-1]["open_time"],
        "record_count": len(candles),
        "dataset_hash": h,
        "candles": candles,
    }
    path = OUT_ROOT / venue / "BTCUSDT" / "H1" / f"{d0}_{d1}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    log(f"{venue}: saved {len(candles)} candles -> {path} (hash={h})")
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--venue", default="all")
    args = ap.parse_args()
    venues = list(VENUES) if args.venue == "all" else [args.venue]
    for v in venues:
        log(f"=== {v} start")
        try:
            candles = VENUES[v]()
            candles = qc(candles, v)
            save(v, candles)
        except Exception as e:
            log(f"=== {v} FAILED: {e!r}")
    log("done")


if __name__ == "__main__":
    main()
