# BOT BLUEPRINT — EXCHANGE ADAPTERS

6 адаптеров, все реализуют СУЩЕСТВУЮЩИЙ `trading_engine/exchange/base.py` (sync, Decimal-модели из `exchange/models.py`). Источники фактов: `EXCHANGE_DATA/EXCHANGE_AUDIT_SUMMARY.md`, `AGENTS/AGENT-02`, `AGENTS/AGENT-03` (проверка 2026-11-08, публичные API без ключей). ⚠️ = не подтверждено документацией/пробой — проверять при реализации.

---

## Сводная таблица

| | Bybit | OKX | KuCoin Futures | HTX (usdt_swap) | BingX (swap v2/v3) | WEEX (capi/v3) |
|---|---|---|---|---|---|---|
| USDT-перп формат | BTCUSDT | BTC-USDT-SWAP | XBTUSDTM | BTC-USDT | BTC-USDT | BTCUSDT |
| Klines endpoint | /v5/market/kline | /api/v5/market/history-candles | /api/v1/kline/query | /linear-swap-ex/market/history/kline | /openApi/swap/v2/quote/klines | /market/historyKlines (⚠️ игнорирует время — только recent; история ТОЛЬКО historyKlines) |
| Klines limit | 1000 | 100 | 500 (weight 3) | 2000 | 1000 | 1000 |
| Klines глубина BTC | 2020-03 | 2019-11 | 1d: 2020-03; интрадей: 2024-08 | 2020-10 (разрыв мар–окт) | ~2024-04 | ~2020-01 |
| Funding история | с листинга, ≤200/запрос | ~3 мес (8ч период) | с 2020-03, полная | с 2020-10, полная | ~14 мес (с 2025-08) | ~6 мес (кап startTime 365 дн, факт ≈565 записей), 8ч |
| OI история | с листинга (интервалы 5m–1d, cursor) | ~6 мес (Rubik) | нет (404) | ~6 мес (≤180 тиков) | только текущее | только текущее |
| Стакан snapshot | REST/WS 1000 | REST 400 / WS tbt | REST 150 / WS l2 | REST 150 / WS hf | v2 depth (⚠️ лимиты) | 15 default / 200 max (иначе ошибка) |
| Комиссии VIP0 maker/taker | 0.02/0.055% (в движке) | 0.02/0.05% ⚠️ | 0.02/0.06% [API] | 0.02/0.06% | ~0.02/0.05% ⚠️ | ⚠️ («0% maker» маркетинг, /fee 404) |
| Rate limits | 200 req (в движке) | per-endpoint IP (50011); WS ≤3 conn/с | весовые, 429 | UNKNOWN ⚠️ | весовые ⚠️ | ~10 req/s [PART] |
| Demo | ✅ demo trading | ✅ `x-simulated-trading: 1` (WS wspap.okx.com) | частично ⚠️ (REST-demo NXDOMAIN) | ❌ нет | ✅ VST `open-api-vst.bingx.com` | частично ⚠️ (CCXT capi/v3/sim/, не проверено) |

---

## Что реализуем для каждого адаптера (минимальный read-path + write-path)

Все адаптеры: `get_balance`, `get_instrument_info`, `get_klines`, `get_funding_history`, `get_positions`, `get_order`, `create_order`, `cancel_order`, `poll_order`. Опционально (по мере надобности стратегий): `get_executions`, `get_closed_pnl`, `get_open_interest`, depth-snapshot.

### 1. Bybit (`bot/venues/bybit/`) — референс
- **Опирается на существующее:** код `exchange/bybit.py` (pybit V5) — переносится как есть, добавляется загрузка ключей через `secrets/loader.py`.
- Новое: выбор base URL по режиму (mainnet / demo-trading URL из конфига `venues.yaml`).

### 2. OKX (`bot/venues/okx/`)
- REST v5: candles (≤100/запрос → пагинация циклом, `before`-курсор), funding-rate-history, account/balance, trade/order (client OID `clOrdId`).
- **Особенности:** заголовок `x-simulated-trading: 1` для demo; OKX v5 требует подписи запросов (HMAC-SHA256, base64) — свой signer; ⚠️ комиссии VIP0 проверить вручную перед включением расчёта издержек; rate-limit 50011 per-endpoint → per-endpoint троттлинг, не глобальный.

### 3. KuCoin Futures (`bot/venues/kucoin/`)
- REST: kline/query, funding-rates (полная история), positions, orders. Подпись: HMAC + passphrase-заголовок.
- **Особенности:** ⚠️ demo REST недоступен (NXDOMAIN) — demo невозможен, paper-контур только; весовые rate limits (429) → адаптивный backoff по ответу; интрадей-kline история с 2024-08 (для бэктестов учитывать).

### 4. HTX (`bot/venues/htx/`)
- REST usdt_swap v1 (линейные свопы): history/kline, swap_historical_funding_rate (page ≤50, полная с 2020-10), positions/orders.
- **Особенности:** demo НЕТ — live-адаптер реализуется, но paper-контур через `PaperVenueAdapter`; ⚠️ rate limits не извлечены → стартовый лимит консервативный (2 req/s), наблюдение; подпись v1 (HMAC + signature-модуль).

### 5. BingX (`bot/venues/bingx/`)
- REST swap **v2/v3** (v1 мёртв): quote/klines, quote/fundingRate, trade orders. **VST-демо:** отдельный base URL `open-api-vst.bingx.com`.
- **Особенности:** klines-история только с 2024-04 (ограничение бэктестов, не runtime); funding интервал читать из `quote/contracts` (`fundingIntervalHours`); ⚠️ лимиты depth v2/v3 отличаются — фиксировать snapshot-формат v2; ⚠️ тонкая ликвидность альтов → min_notional фильтр + counterparty-лимит.

### 6. WEEX (`bot/venues/weex/`)
- REST capi/v3: klines ТОЛЬКО через `/market/historyKlines` с **обязательной парой startTime+endTime** (≤1000); `/market/klines` без параметров времени — не использовать для истории; fundingRate (окно ≈6 мес); depth 15/200 (другие значения → ошибка).
- **Особенности:** ⚠️ demo не подтверждён (sim-пути по CCXT) — paper-контур только; ⚠️ комиссии неизвестны — до подтверждения расчёт издержек консервативный taker-максимум; ~10 req/s; **counterparty-риск (жалобы на вывод) → самый жёсткий лимит остатка средств, см. RISK_MANAGER.md**.

---

## Rate-limit-стратегия (общая, `bot/venues/base_mixin.py`)

- Существующий паттерн из `scripts/collect_mx_klines.py` переиспользуем: per-venue интервал (WEEX 1.5 с+ ограничение ~10 req/s; OKX per-endpoint; KuCoin по 429-retry), глобальный зазор 0.5 с.
- Token-bucket per venue, конфиг из `venues.yaml`; при 429 — backoff на заголовке `Retry-After` если есть, иначе exp. backoff.
- Все адаптеры sync (соответствие ABC); параллельность — поток per venue.

## Аутентификация

- Единый интерфейс `Signer` per venue (HMAC-варианты разные: Bybit/OKX/HTX/WEEX/BingX — query-sign, KuCoin — passphrase). Реализации в `bot/venues/<v>/signer.py`. Ключи только из `secrets/loader.py` (env / Credential Manager). Тест-страж: fixture-логи не содержат ключей.

## Порядок реализации адаптеров

**Bybit → OKX → KuCoin → HTX → BingX → WEEX** (как в выводе EXCHANGE_AUDIT_SUMMARY.md: данные + demo + надёжность).

1. **Bybit** — код уже есть; цель: read-path + paper-execution через demo-trading.
2. **OKX** — лучший demo (x-simulated-trading), глубокие klines; критичен для HYP-M-003 (funding-спреды Bybit↔OKX уже пишутся WS-регистратором).
3. **KuCoin** — лучшая funding-история (для research-контура cross-exchange funding на истории).
4. **HTX** — демо нет; адаптер нужен для cross-exchange стратегий, но проходит только paper + live-gate позже.
5. **BingX** — VST-демо живой; слабая история не мешает runtime.
6. **WEEX** — последний: минимальные данные, неподтверждённые комиссии/demo, максимальный counterparty-риск.

Критерий готовности адаптера: unit-тесты на fixture-ответах (нормализация, сортировка баров, is_closed-фильтр), плюс integration-тест read-path против публичного API, плюс для demo-venue — round-trip ордера в demo-режиме (после отдельного разрешения на demo).
