# WS RECORDER — prospective-запись funding/OI/ликвидаций/сделок

Статус: **ЗАПУЩЕН 2026-11-08/09** (фоновый процесс сессии; для 24/7 нужен системный сервис — см. «Автозапуск»).
Код: `src/trading_engine/collectors/ws_recorder.py`, запускатор `scripts/start_ws_recorder.py`.

## Что записывается

| Биржа | Канал | Символы | Содержимое (norm) |
|---|---|---|---|
| Bybit (wss stream.bybit.com/v5/public/linear) | tickers | BTCUSDT, ETHUSDT | lastPrice, fundingRate, nextFundingTime |
| Bybit | allLiquidation | BTCUSDT, ETHUSDT | side, price, size, n_items |
| Bybit | publicTrade | BTCUSDT | agg-сделки: side, price, size, trade_id |
| Bybit | orderbook.50 | BTCUSDT | best bid/ask, n уровней, u-seq (детектор гэпов) |
| Bybit | openInterest (REST-поллинг 5 мин) | BTCUSDT, ETHUSDT | OI snapshot |
| OKX (wss ws.okx.com/ws/v5/public) | tickers | BTC-USDT-SWAP, ETH-USDT-SWAP | last, **openInterest** (⚠ funding_rate у OKX-тикеров НЕТ — QC 2026-11-09) |
| OKX | trades | BTC-USDT-SWAP | сделки |
| **Funding-панель (REST-поллинг 15 мин)** | funding.* | BTC+ETH | funding_rate + estimated для HTX (BTC-USDT/ETH-USDT), KuCoin (XBTUSDTM/ETHUSDTM), OKX (BTC/ETH-USDT-SWAP) |
| Bybit insurance | insurance.linear | — | баланс insurance fund (snapshot; истории у API нет — только prospective-запись). ⚠ Файлы пишутся в каталог venue `bybit_insurance/` (ключ конфига) — косметика, при следующем рестарте можно переименовать в "bybit". |

Дата-предел: funding-панель добавлена 2026-11-10; insurance — с 2026-11-10. Ранее накопленные данные этих потоков отсутствуют (начало записи = даты добавления).

Каждая строка JSONL: `{recv_ts (UTC ms), venue, stream, raw (оригинальный payload), norm}`.
Путь: `research/datasets/raw/ws/<venue>/<stream>/<YYYY-MM-DD>.jsonl`; логи: `research/datasets/raw/ws/logs/`.

## Исправленные дефекты (2026-11-09, найдены тестом)
1. `ping send failed: 'str' object cannot be interpreted as an integer` — Bybit ping отправлялся dict'ом; websocket-client требует str/bytes → исправлено на `json.dumps({"op":"ping"})`.
2. **Молчаливая потеря всей пачки подписок Bybit**: устаревшие топики `liquidation.{sym}` (ретирены, «handler not found») и `orderbook50.{sym}` (неверный формат) отклоняли ВЕСЬ batch subscribe → ноль данных без ошибок. Исправлено на `allLiquidation.{sym}` и `orderbook.50.{sym}`; добавлено логирование control-frames (`success:false`).

## Ограничения
- Процесс привязан к сессии/машине — при закрытии сессии запись останавливается.
- OKX `liquidation-orders` — требует авторизации, НЕ подписан (публичных ликвидаций OKX нет; REST даёт ~сутки).
- OI Bybit — REST-поллинг раз в 5 мин (WS-топика OI нет).
- Ликвидации — редкие события; для статистики HYP-M-004 нужны недели записи.

## Запуск
```
.venv/Scripts/python.exe -X utf8 scripts/start_ws_recorder.py            # постоянно
.venv/Scripts/python.exe -X utf8 scripts/start_ws_recorder.py --test 45  # тестовое окно
```

## План автозапуска (24/7)
Windows: Task Scheduler → `C:\Users\rusla\Trade\Trade3\.venv\Scripts\pythonw.exe C:\Users\rusla\Trade\Trade3\scripts\start_ws_recorder.py`, триггер «при входе», настройка «перезапуск при сбое». Либо NSSM-сервис. До настройки — вручную в начале каждой исследовательской сессии.

## Назначение данных
- HYP-M-003 (cross-exchange funding carry): fundingRate-спреды Bybit↔OKX из tickers.
- HYP-M-004 (post-liquidation reversal): allLiquidation + до/после-движения по trades.
- Track A (spread capture): orderbook.50 + trades для анализа спредов/лагов.
- ОФ-исследования (HYP-M-005): taker-поток из trades/publicTrade.
