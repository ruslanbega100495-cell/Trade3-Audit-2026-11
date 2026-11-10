# DATASETS — мультибиржевое исследование

## H1 klines BTCUSDT (скачано 2026-11-09, scripts/collect_mx_klines.py, лог: collect_mx_klines.log)

| venue | путь | бары | период | sha256-16 | ограничения |
|---|---|---|---|---|---|
| bybit | research/datasets/raw/bybit/BTCUSDT/H1/2024-04-01_2026-11-09.json | 22 852 | 2024-04-01→2026-11-09 | 5f4d29c127893565 | — |
| okx | research/datasets/raw/okx/BTCUSDT/H1/2024-04-01_2026-11-09.json | 22 852 | 2024-04-01→2026-11-09 | cf00d8ac8c8c3d55 | — |
| kucoin | research/datasets/raw/kucoin/BTCUSDT/H1/2024-08-05_2026-11-09.json | 19 826 | 2024-08-05→2026-11-09 | fd22aa7e419ef6b2 | интрадей API KuCoin стёрт до 2024-08-05 |
| htx | research/datasets/raw/htx/BTCUSDT/H1/2026-08-17_2026-11-09.json | 1 999 | 2026-08-17→2026-11-09 | a778ba2f9da927de | **HTX 60min API игнорирует from/to** — только ~2000 последних баров; глубокой H1-истории нет (1d — с 2020-10) |
| weex | research/datasets/raw/weex/BTCUSDT/H1/2024-04-01_2026-11-09.json | 22 851 | 2024-04-01→2026-11-09 | aa1cbc1aebcbad0f | historyKlines: без limit, 100 баров/запрос |
| bingx | research/datasets/raw/bingx/BTCUSDT/H1/2024-04-27_2026-11-09.json | 22 218 | 2024-04-27→2026-11-09 | 4f4f33ee5daccd3a | история API с ~2024-04-20 |

Схема файла: {symbol, timeframe, source, download_time, start, end, record_count, dataset_hash, candles:[{open_time(ISO UTC), open, high, low, close, volume, turnover}]}.
Хеш: sha256(json.dumps([(open_time, close),...], separators=(",",":")))[:16] — совместимо с research/scripts/collect_bybit.py.

## Найденные особенности качества данных (2026-11-09)
- **KuCoin H1 klines — систематическое смещение +2.66 bps** относительно Bybit last-close (lag-1 автокорреляция дислокации 0.82; контроль WEEX: смещение −0.03 bps). Вероятно mark-price/index-основа свечей. Для сравнений с KuCoin вычитать константу; на вывод M-001 (REJECTED) не влияет (p99 |дислокации| 6.5 bps включала смещение).
- HTX H1 (см. таблицу) — только ~2000 последних баров через API.

## Prospective WS-запись (с 2026-11-09, см. WS_RECORDER.md)
research/datasets/raw/ws/<venue>/<stream>/<YYYY-MM-DD>.jsonl — Bybit (tickers, allLiquidation, publicTrade, orderbook.50, openInterest-поллинг), OKX (tickers, trades); BTC+ETH. Формат строки: {recv_ts, venue, stream, raw, norm}.

## Существующие Bybit-датасеты (до мультибиржевого цикла)
- BTCUSDT H4/OI/spot/funding 2024-01→2026-09 (hash e182346101e28d26 для H4) — см. research/reports/V6_DATA_QC.md.
- 25 символов H4+funding 2022-11→2025-04 (для HYP-L-001; пауза).
