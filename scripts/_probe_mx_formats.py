"""Зонд 4: KuCoin окно 2024-09 (формат + лимит)."""
import requests, json

S = requests.Session(); S.headers.update({"User-Agent": "Mozilla/5.0"})
F = 1725148800000  # 2024-09-01
T = F + 40 * 24 * 3600_000
r = S.get("https://api-futures.kucoin.com/api/v1/kline/query",
          params=dict(symbol="XBTUSDTM", granularity="60", **{"from": str(F)}, **{"to": str(T)}), timeout=20)
print(r.status_code)
d = r.json()
data = d.get("data", [])
print("n =", len(data))
print("first:", data[0] if data else None)
print("last:", data[-1] if data else None)
