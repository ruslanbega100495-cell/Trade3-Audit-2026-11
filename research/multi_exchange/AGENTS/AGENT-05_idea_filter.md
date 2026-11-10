# AGENT-05 — IDEA FILTER: аудит локальных идей и транскрибаций

Дата: 2026-11-08. Метод: чтение локальных документов (мастер-планы V8/V9/V10, промпты, STRATEGY_SPEC_A/B, SOURCE_EVIDENCE, preregistration V10.7/V10.8/V10.10).

## Транскрибации автора — НАЙДЕНЫ
- experiments/illiquid_spread/reports/transcript_video_A.json (1193 сегм., Track A: CEX spot spread collection, Video `loVcAj_Cgmc`).
- experiments/illiquid_spread/reports/transcript_video_B.json (1643 сегм., Track B: DEX perp scalping, Video `D-zD6uAX19M`).
- Подтверждены в SOURCE_EVIDENCE.md (claims A-01…A-14, B-01…B-14, timecodes, SOURCE_CONFIRMED). «Текстовый документ.txt» — несвязан (content_factory), исключён.

## Идеи из локальных документов (полный список → статус)

**Видео-треки:**
- Track A (Video A, CEX spot spread capture): SPEC_ONLY/BLOCKED_BY_DATA. Прокси-тест H1 Bybit: −1.295 USDT/228 RT, fill_confidence=0.30 — не финальный вердикт по Track A. Заявленная доходность («$20 на 1000 операций») не принята. Нужен prospective L2-capture.
- Track B (Video B, DEX perp scalping по лагу MM): спред CONFIRMED (0.18% AsterDEX, 4.6× Bybit), лаг FALSIFIED (median −43 мс; V10.10: 92.6% эпизодов DEX реагирует раньше детекта). Осталась ветка «conditional lag при быстрых движениях» (V10.10 preregistered) и смена инструмента. Заявленная доходность не принята.

**illiquid-пакет:** H1 (−1.295 USDT), H2 (avg_net −32.7 bps, WR 11.6%), H3 (0 событий), H4-v1 FALSIFIED (WR 20%), H4-v2 DATA INSUFFICIENT, H5 spike/base INSUFFICIENT_N (effective n≈4–6, доминирует outlier 00018=182%), H-RS/H-MR NOT_VALIDATED (после исправления look-ahead), H-PRE EXPLORATORY (in-sample), H-SPIKE-BASE v1 INVALID (look-ahead прецедент), H-WICK/H-POST/H-LIST не проверены.

**V3-реестр:** см. AGENT-01 (14 REJECTED/FAILS, H16 PROMISING, L-001 на паузе, A-001 — 2 блокера: WF-B не задокументирована; конфликт DECISION.md «WEAK» vs CANDIDATE_GATE «PRIMARY»).

**Внешние источники:** IKIGAI Elliott Wave — NOT_OPERATIONALIZABLE (субъективная разметка); QS Strategy 1 — DUPLICATE_OF (HYP-D+A); QS Strategy 2 — за paywall; ICT/SMC — FVG placebo-совместим, sweep-варианты отвергнуты (K-002/K-005); MA crossover (K-001) REJECTED; TSMOM → H16 PROMISING.

**V10-треки C–J:** C — INSUFFICIENT_N/EDGE_NOT_CONFIRMED; D (межрыночный арбитраж) — не зарегистрирован; E (liquidation flows) — кандидат, не зарегистрирован; F (native-crypto OFI) — кандидат, тестируемость обоснована литературой; G (funding/carry) — H15 REJECTED, L-001 зарегистрирована непрогнанной; H (event momentum) — DUPLICATE-риск с H5; I (lead–lag) — фактически опровергнут V10.7–V10.10; J — не формулировался отдельно.

## Противоречия версий планов
V8→V9→V10 — эволюция без прямых логических конфликтов: V9 добавляет addendum §13–17; V10 добавляет треки E–J, переписывает §13, меняет статус H2 (n=50→69) и H5 (n=5→8). Принципиальное расхождение: SPIKE_PROMPT_V3–V5 трактуют recurring-spike как «метод Клевцова», V10 §0 запрещает называть H5 «стратегией Клевцова». V10 — актуальнее.

## Экономическая оценка
Наиболее обоснованы: Track A (при BLOCKED_BY_DATA), HYP-H16 (PROMISING, не edge), HYP-L-001 (чистый механизм, на паузе), Track F (литературно). Слабо обоснованы: Track B (механизм опровергнут), Track C/H-RS (look-ahead-контаминация, selection bias, n≈4–6).

## Рекомендации
Подтверждённого net edge в проекте нет. Живые направления: H16→VALIDATION (D-001), Track A prospective L2, cross-exchange направления (новые HYP-M-*). Все заявленные доходности транскрибаций проверять только через DATA→…→LIVE цепочку.

## Ограничения
Оценка экономической обоснованности — качественная; количественная проверка — задача последующих этапов.
