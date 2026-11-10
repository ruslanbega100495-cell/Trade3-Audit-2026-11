# AGENT-02 — EXCHANGE DATA: аудит OKX / KuCoin / HTX

Дата проверки: 2026-11-08 (UTC). Метод: официальная документация + эмпирические пробы публичных REST/WS (без ключей). Всё неподтверждённое помечено.

## OKX (docs-v5)
- USDT-перпы: да (`BTC-USDT-SWAP`).
- Klines: `/api/v5/market/history-candles`, ≤100 баров/запрос; **эмпирика BTC 1D: с 2019-11-30**.
- Trades: `/market/history-trades`, ≤100/запрос; **глубина ≈ 3 месяца**.
- Стакан: REST books до 400 ур. (эмпирика), WS books-l2-tbt; истории стакана нет.
- Funding: текущий + `/public/funding-rate-history`; **глубина ≈ 3 месяца**; период 8ч.
- OI: текущий `/public/open-interest`; история только Rubik `/rubik/stat/contracts/open-interest-volume` (OI+vol, 5m–1D); **≈ 6 месяцев**.
- Ликвидации: REST `/public/liquidation-orders` **≈ сутки**; история только WS business real-time.
- Комиссии VIP0: maker 0.02%/taker 0.05% — по вторичным источникам, **ручная сверка нужна** (SPA-страница).
- Rate limits: per-endpoint по IP (50011), WS ≤3 conn/с, ≤480 subscribe/ч.
- Demo: **да** — `x-simulated-trading: 1`, WS wspap.okx.com.

## KuCoin Futures (docs-new)
- USDT-перпы: да (`XBTUSDTM`).
- Klines: `/api/v1/kline/query`, ≤500 баров (weight 3); **1d с 2020-03-30; интрадей ТОЛЬКО с ~2024-08-05 (вайп старых)**.
- Trades: `/api/v1/trade/history` — offset игнорируется, только последние минуты. История только WS.
- Стакан: level2 snapshot + sequence; WS level2/level3; истории нет.
- Funding: текущий + `/contract/funding-rates`; **полная история с листинга (2020-03-30, записи с 2020-05-04)** — лучшая среди шести.
- OI: **отсутствует** (404 на все пробы).
- Ликвидации: публичного REST нет; WS — не подтверждено.
- Комиссии VIP0: **подтверждено API**: maker 0.0002 / taker 0.0006.
- Demo: частично (WS-demo есть в доке; REST base api-demo-futures не резолвится — NXDOMAIN).

## HTX (huobiapi.github.io usdt_swap v1 + bulletin 94916436903925)
- USDT-перпы: да (`BTC-USDT`).
- Klines: `/linear-swap-ex/market/history/kline`, size ≤2000 (эмпирика); **1d с 2020-10-20; разрыв мар–окт 2020** (инструмент с весны 2020).
- Trades: `/history/trade` — только последние (≤2000, без временных параметров).
- Стакан: depth до 150 (эмпирика); WS high_freq инкременты; истории нет.
- Funding: текущий + `/swap_historical_funding_rate` (page ≤50); **6628 записей, полная с 2020-10-22**.
- OI: текущий + `/swap_his_open_interest`; **≤180 тиков ≈ 6 месяцев**.
- Ликвидации: v3 `/swap_liquidation_orders` (v1 выведен — bulletin); фактически часы–сутки; WS push.
- Комиссии VIP0: **подтверждено статьёй HTX**: maker 0.02% / taker 0.06%.
- Demo: **нет** (testnet.hbdm.com не резолвится).
- Rate limits: не извлечены (SPA/GitHub-обрезка) — UNKNOWN.

## Сравнительная глубина (BTC perp, эмпирика)
Klines 1d: OKX 2019-11 > KuCoin 2020-03 > HTX 2020-10. Funding history: KuCoin (2020) > HTX (2020-10) > OKX (~3 мес). OI history: OKX ~6мес, HTX ~6мес, KuCoin нет. Ликвидации истории нет нигде.

## Рекомендации
OKX — первый кандидат для cross-exchange пар (глубина klines + demo). KuCoin — критична для funding-истории. HTX — разрыв 2020 в QC. Всё микроструктурное (стакан/тики/ликвидации) — только prospective WS-запись.

## Ограничения
Не подтверждено: точные rate limits HTX; OKX fees VIP0; KuCoin demo REST; HTX 1m-глубина; KuCoin WS ликвидации/OI.
