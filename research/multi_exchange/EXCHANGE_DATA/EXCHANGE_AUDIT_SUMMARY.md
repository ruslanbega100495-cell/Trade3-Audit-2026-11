# EXCHANGE AUDIT SUMMARY — шесть бирж

Дата проверки: 2026-11-08. Детальные отчёты: `../AGENTS/AGENT-02_exchange_audit_okx_kucoin_htx.md`, `../AGENTS/AGENT-03_exchange_audit_weex_bingx_bybit.md`. Статусы: [DOC] подтверждено документацией, [API] проверено реальным запросом, [PART] частично, [UNK] неизвестно.

## Сводная таблица

| Данные | Bybit | OKX | KuCoin | HTX | WEEX | BingX |
|---|---|---|---|---|---|---|
| USDT-перпы | ✅ [API] | ✅ [API] | ✅ [API] | ✅ [API] | ✅ [API] | ✅ [API] |
| Klines глубина (BTC) | 2020-03 [API] | 2019-11 [API] | 1d: 2020-03; интрадей: 2024-08 [API] | 2020-10 (разрыв мар–окт) [API] | ~2020-01 [API] | ~2024-04 [API] |
| Funding история | с листинга [API] | ~3 мес [API] | с 2020-03, полная [API] | с 2020-10, полная [API] | ~6 мес (кап 365д) [API] | ~14 мес [API] |
| OI история | с листинга [API] | ~6 мес (Rubik) [API] | нет [API] | ~6 мес [API] | нет [API] | нет [API] |
| Сделки история | recent [DOC]; архив на сайте | ~3 мес [API] | минуты [API] | последние N [API] | recent [API] | recent [API] |
| Стакан snapshot | REST 1000 / WS 1000 [DOC] | REST 400 / WS tbt [API] | REST 150 / WS l2 [API] | REST 150 / WS hf [API] | REST 15/200 [API] | REST / WS [PART] |
| Ликвидации | WS rt [DOC] | REST ~1сут + WS [API] | нет [UNK:WS] | часы–сутки + WS push [API] | не подтв. | не подтв. |
| Комиссии maker/taker | 0.02/0.055% (в движке) | 0.02/0.05% [PART] | 0.02/0.06% [API] | 0.02/0.06% [DOC] | UNK («0% maker» маркетинг) | ~0.02/0.05% [PART] |
| Rate limits | 200/1000 на req [DOC] | per-endpoint IP, 50011 [DOC] | весовые, 429 [DOC] | UNK | ~10 req/s [PART:CCXT] | весовые [PART:CCXT] |
| Demo/testnet | ✅ demo trading [DOC] | ✅ x-simulated-trading [DOC] | частично [PART] | нет [API] | частично [PART:CCXT] | ✅ VST open-api-vst [API] |

## Ключевые выводы
0. **Уточнения от сбора 2026-11-09 (эмпирика загрузки):**
   - HTX `history/kline` period=60min **игнорирует from/to**: всегда отдаёт newest `size` баров → глубокой истории H1 нет (доступно ~2000 последних часов ≈ 83 дня). История 1d при этом полная с 2020-10. Для H1-исследований HTX ограничен последними ~3 месяцами.
   - WEEX `historyKlines` **не принимает `limit`** (400 «Parameter 'limit' is invalid») и возвращает голый JSON-список; только symbol+interval+startTime+endTime.
   - Bybit kline отдаёт newest-first в окне [start,end] — пагинация только назад от end; KuCoin интрадей реально начинается 2024-08-05 (пустые окна раньше).
1. **Klines-backtest возможен на 5/6 биржах** с 2020 (BingX — только с 2024-04). Единый 2024-04→2026-11 контур доступен на всех шести.
2. **Funding/OI/ликвидации cross-exchange — только prospective** (WS-запись). Историческая проверка funding-carry между биржами невозможна задним числом.
3. **Исторического стакана нет ни у одной** — order-flow/L2-гипотезы только с момента запуска регистратора.
4. Порядок подключения (по данным + demo + надёжности): Bybit → OKX → KuCoin → HTX → BingX → WEEX (см. DECISIONS/D-002 при появлении).
5. Counterparty-риск WEEX (жалобы на вывод) → в риск-модели жёсткий лимит остатка средств; BingX — тонкая ликвидность альтов.
