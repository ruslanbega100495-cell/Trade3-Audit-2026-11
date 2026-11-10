# AGENT-03 — EXCHANGE DATA: аудит WEEX / BingX / подтверждение Bybit

Дата проверки: 2026-11-08. Метод: официальные доки + эмпирические запросы к публичным API; CCXT как референс endpoint'ов. Всё неподтверждённое помечено.

## Bybit — полнота покрытия подтверждена
Адаптер проекта (pybit V5) корректен: `/v5/market/kline` (limit ≤1000), `/v5/market/funding/history` (limit ≤200, передавать startTime И endTime), `/v5/market/open-interest` (limit ≤200, cursor, интервалы 5m–1d). Klines BTCUSDT: минимум с 2020-03-24. Неподключённое, но доступное: WS `liquidation.{symbol}` real-time, WS стакан 1000 ур., `/v5/market/insurance`.

## WEEX (api-contract.weex.com, capi/v3)
- USDT-перпы: да (BTCUSDT, формат без дефиса).
- Klines: `/market/klines` ИГНОРИРУЕТ startTime/endTime (всегда последние N); история только `/market/historyKlines` — требует ОБА startTime+endTime, limit ≤1000. **Глубина: данные за январь 2020 есть, декабрь 2019 пусто → с ~2020-01**.
- Trades: только recent snapshot; истории нет.
- Стакан: `/market/depth` — default 15 ур., макс. 200 (другие значения → ошибка). Истории нет. WS — не подтверждено.
- Funding: `/market/fundingRate` отдаёт историю, limit ≤1000, **startTime капнут последними 365 днями; фактическое окно ≈ 6 месяцев** (~565 записей при лимите 1000). Интервал 8ч.
- OI: только текущее значение. Истории нет.
- Ликвидации: публично не подтверждено (fetchLiquidations=false).
- Комиссии: не подтверждено (маркетинг «0% maker»; /fee → 404).
- Demo: частично (CCXT sim-пути `capi/v3/sim/`, в доках не перепроверено).
- Rate limits: по CCXT ~10 req/s публичные — частично подтверждено.

## BingX (open-api.bingx.com, swap v2/v3)
- USDT-перпы: да (BTC-USDT). ⚠️ v1 quote-эндпоинты мёртвы («api is not exist»), актуальные v2/v3.
- Klines: `/openApi/swap/v2/quote/klines`, limit ≤1000. **Глубина: с ~2024-04-20 всё раньше пусто (~2,5 года)** — ранняя история через API недоступна.
- Trades: только recent; исторических тиков нет (v3 historicalTrades мёртв).
- Стакан: v2 quote/depth snapshot (работает); v3 вернул пустой books — лимиты отличаются. Истории нет.
- Funding: `/quote/fundingRate` — история, limit ≤1000. **Глубина ≈ с 2025-08-01 (~14–15 мес)**. Интервал в `quote/contracts` → fundingIntervalHours.
- OI: только текущее. Истории нет.
- Ликвидации: публично не подтверждено.
- Комиссии: ~0.02%/0.05% — не перепроверено (SPA).
- Demo: **подтверждено живыми запросами**: `https://open-api-vst.bingx.com` (VST) отвечает klines+depth.

## Выводы
WEEX пригоден для klines-backtest с 2020 (только historyKlines с парой start+end); funding/OI исторически слаб. BingX — самая ограниченная история (klines 2024+, funding ~1 год), годится только для исследований 2024→ныне и prospective-сбора. Bybit — полное покрытие.

## Ограничения
Не подтверждено: точные maker/taker WEEX/BingX; макс. глубина BingX v2 depth; детали WS WEEX; публичные ликвидации WEEX/BingX; rate limits из первоисточника.
