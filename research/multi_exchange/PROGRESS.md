# PROGRESS — точка остановки

Обновляется в конце каждого крупного этапа. Формат: `## <дата> — <этап>` + сделано/итог/следующие задачи.

## 2026-11-09 — Этап 7: верификация + старт нового цикла поиска

**Сделано:**
- **WS Recorder ВЕРИФИЦИРОВАН работающим** (не только файлы): процесс жив; все 8 потоков пишут данные, актуальные до текущей секунды; ~350k событий/сутки; 24+5 событий ликвидаций BTC/ETH за день; OI-поллинг каждые 5 мин работает; 1 автоматический reconnect (07:28) с восстановлением; 0 гэпов orderbook-sequences; 0 rejected-подписок после фиксов. 179 МБ данных. Минорно: OKX отвечает текстовым "pong" (шлём "ping" строкой — работает, но шум в логе).
- QC-находка: **KuCoin H1 klines имеют систематическое смещение +2.66 bps** (вероятно mark/index-основа свечей; autocorr 0.82) — задокументировано в DATASETS.md; на отвергнутый M-001 не влияет.
- Запущены 3 параллельных агента (фон): AGENT-08 Market Research (новые возможности: rebates, funding MM, листинги, term structure), AGENT-09 Strategy Researcher (гипотезы вне списка), AGENT-13 HYP-M-003 funding-spread descriptive (регистрация + анализ WS-данных).

**Следующие задачи:**
1. Дождаться агентов → свести результаты.
2. Историческая проверка funding dispersion Bybit↔KuCoin↔HTX (funding-истории полные с 2020/2022 — скачиваемые; ≥200 меток сразу) — самостоятельная регистрация HYP-M-005 перед прогоном.
3. Итоговый отчёт A–H.

## 2026-11-09 (вторая половина) — Этап 7 продолжение: HYP-M-005 завершена

**Сделано:**
- Funding-истории скачаны и проверены: KuCoin 3 130 меток (hash 2bbf79a3f49bf28c), HTX 3 131 меток; Bybit локально (hash 5b8057d195a7c8a9). Дубли 0, знаки конвенций единообразны.
- QC-находка: **метки funding KuCoin смещены на 4ч** (04/12/20 UTC vs 00/08/16 у Bybit/HTX) — помарочное сравнение невозможно; единица анализа — суточная сумма funding (точное выражение carry-PnL при неизменной позиции).
- HYP-M-005 прогон (456 суток, 2024-01→2025-04, регистрация до анализа): значимая статистическая дисперсия есть (bybit−kucoin −1.11 bps/день, CI [−1.47, −0.75]; kucoin−htx +1.07 [0.67, 1.46]), но mean abs 1.7–2.8 bps/**день** против критерия >10 bps/8ч — **REJECTED (magnitude below cost floor)**. Идеальное следование знаку: +0.1–0.2 bps/день (~0.4–0.7% годовых) — ниже безрисковой ставки. Bybit−HTX: dispersion статистически нулевая. Стационарность — AR(1)-proxy, НЕ полноценный ADF (ограничение зафиксировано).
- Следствие: историческое пле funding carry на BTC-мейджорах закрыто; априор M-003 (Bybit↔OKX) снижен; остаток направления — альты/экзотика.
- Отчёт BACKTESTS/HYP-M-005_funding_dispersion.md, реестр обновлён.
- Три агента (11, 12, 13) возобновлены после сброса квоты, работают в фоне.

## 2026-11-10 — Этап 8 (economy mode): M-003 сведена, M-006/M-007 прогнаны, регистратор расширен

**Сделано:**
- HYP-M-003 (Bybit↔OKX funding spread, REST-мост 60 дн): mean abs 0.25 bps, 0% меток ≥10 bps — консистентно с M-005, low prior подтверждён; QC: OKX-тикеры НЕ содержат funding (0/98k) — fixed поллером.
- WS-регистратор расширен: funding-панель 4 бирж (HTX/KuCoin/OKX поллеры 15мин, BTC+ETH) + Bybit insurance snapshot. Пофикшено: kucoin funding URL (symbol в path), добавлен OKX funding (extract data[0]). Работает, 7+ потоков.
- HYP-M-006 (OI-Δ lead): REJECTED — |t|≤0.74 все горизонты, max контраст 8.6 bps < 42.
- HYP-M-007 (tier-2 turnover-share rotation): REJECTED по kill-критерию (t=2.4<3); перекрывающийся t=7.1 — артефакт (зафиксировано). Единственный borderline-кандидат на prospective re-test (≈5 мес накопления объёмов).
- Отчёты: BACKTESTS/HYP-M-00{3,6,7}*.md; реестры обновлены (M-005/6/7 → REJECTED).

**Точка остановки:**
- [in_progress] Агент-11 (Market Research, AGENT-08) — в фоне; по завершении: свести в MASTER_REPORT (A–H) и закрыть Goal.
- [pending] Итоговый отчёт A–H + проверка файлов + git status.

## 2026-11-10 (финал) — закрытие этапа

- AGENT-08 (Market Research) завершён: `AGENTS/AGENT-08_market_research_r2.md`. Топ-находка: листинговый funding-эффект (21% свежих перпов Bybit funding ≤ −0.74%; селективные позиции 48–72ч). Fee/rebate-сверка — незавершённый блокер.
- HYP-M-008 зарегистрирована (alt funding dispersion, до сбора данных).
- `FINAL_REPORT_E2.md` финализирован (A–H).
- Финальные проверки: 0 пустых файлов; реестр M-001…M-008 консистентен; git: всё untracked (коммиты не делались).
- WS-регистратор работает (фон, 7 funding/insurance + 8 WS потоков, 4 биржи).
- Открытые ветви на будущее (не сейчас): prospective re-test M-007 (не ранее ~2027-04 по объёмам), crash-prediction форма OI-Δ (AUROC, новая регистрация), M-004 post-liquidation (копить ликвидации), S-03 insurance-score (копится с 2026-11-10).



## 2026-11-09 — Этап 6: HYP-M-001 dislocation study (завершён, ОТРИЦАТЕЛЬНЫЙ) + финализация

**Сделано:**
- Докачаны H1 klines всех 6 бирж (после 3 фиксов пагинации: Bybit newest-first→пагинация назад; OKX якорь after=END-1; HTX игнорирует from/to для 60min → только ~2000 баров; WEEX без limit, 100 баров/запрос, окно 99ч). Метаданные+хеши: DATASETS/DATASETS.md.
- HYP-M-001 (зарегистрирован ДО анализа): event study дислокаций H1-закрытий vs медиана лидеров (Bybit/OKX), 2024-04→2026-11.
- Результат: **REJECTED (INSUFFICIENT_EVENTS)** — median |дислокации| 0.4–2.8 bps, p99 ≤ 6.5 bps (<< 10 bps round-trip cost); персистентных событий ≥10 bps за 2,5 года — 1. Критерий ≥200 событий не выполнен в 200 раз. Направление «медленный H1-арбитраж» закрыто для BTC на этих биржах.
- Отчёт BACKTESTS/HYP-M-001_dislocation_study.md, реестр HYP-M-001.yaml → REJECTED, сырые числа hyp_m001_results.json.
- AGENTS/AGENT-07_red_team.md — отчёт Red Team (оба вердикта H16/M-002 стоят).
- MASTER_REPORT.md финализирован.

**Итог цикла:** 3 новые гипотезы протестированы — все 3 REJECTED с доказательствами; 0 подтвержденных стратегий. Не повторять без новых данных/новизны: TSMOM (H16), XS-momentum 4д (M-002), H1 cross-exchange dislocation (M-001).

**Следующие задачи (новая сессия, см. MASTER_PROMPT_NEXT_PHASE.md):**
1. Не прерывать WS-запись (автозапуск через Task Scheduler) — копятся данные для HYP-M-003/004.
2. ≥2–4 недель данных → регистрация HYP-M-003 (funding dispersion carry Bybit↔OKX из WS-тикеров).
3. Реализация бота: этапы 1–2 MASTER PROMPT (каркас + адаптеры Bybit/OKX).

## 2026-11-09 — Этап 5: Red Team аудит + WS-регистратор (завершено)

**Сделано:**
- Red Team (агент-9) независимо пересчитал HYP-H16 VALIDATION и HYP-M-002: все ключевые числа совпали до 4 знаков, look-ahead не найден, DSR реализован точно, funding-недоучёт в H16 не переворачивает вердикт (±2.3% max bound vs −9.24% total). Отчёт: VALIDATION/RED_TEAM_AUDIT_H16_M002.md + audit_*_recalc.py. **Оба вердикта REJECTED СТОЯТ.**
- Одиночная находка M-002: почасовые funding-периоды у части альтов не учитываются моделью (недоучёт, не look-ahead; funding-вклад 2–4% ΣPnL — на выводы не влияет).
- WS-регистратор (collectors/ws_recorder.py) отлажен и **запущен в постоянную запись** (Bybit: tickers/allLiquidation/publicTrade/orderbook.50/OI-поллинг; OKX: tickers/trades; BTC+ETH). Исправлено 2 дефекта: dict-ping (TypeError) и молчаливое отклонение всего batch-subscribe Bybit из-за ретиренных топиков liquidation.*/orderbook50.* → allLiquidation.*/orderbook.50.*. Документация: DATASETS/WS_RECORDER.md.
- Качаются 1h klines 6 бирж для HYP-M-001 (фон, scripts/collect_mx_klines.py → research/datasets/raw/<venue>/).

**Следующие задачи:**
1. [in_progress] HYP-M-001: регистрация + dislocation event study (после завершения загрузки klines)
2. [in_progress] Архитектура бота (агент-10, фон) → BOT_BLUEPRINT/
3. [pending] MASTER_REPORT.md + MASTER PROMPT следующего этапа + финальная проверка сохранения

---
## 2026-11-08 — Этап 4: HYP-H16 VALIDATION (завершён, ОТРИЦАТЕЛЬНЫЙ результат)

**Сделано:**
- Протокольная VALIDATION HYP-H16 (vol-normalized TSMOM, BTCUSDT H4) на периоде 2025-04-01→2025-10-01 (DECISIONS/D-001), замороженный конфиг N=12 vol-scaled (TARGET_VOL 0.20, LEVERAGE_CAP 2.0, VOL_WINDOW 20, MIN_VOL 0.05), модель исполнения и издержек один-в-один с TRAIN; hash датасета проверен.
- Результат: **FAIL_VALIDATION**. n=91, mean net −0.1015%/сделку, 95% CI (t) [−0.506, +0.303], Sharpe −0.830, MaxDD 20.5%, WR 0.429, PF 0.870; при 2× издержках −0.2701%/сделку, Sharpe −2.203. Exploratory N=24 — тоже отрицательно (−0.038%/сделку).
- TRAIN→VALIDATION: знак expectancy перевернулся (+0.2246% → −0.1015%), Sharpe 1.577 → −0.830 — признаки переобучения/нестационарности, edge не подтверждён.
- Отчёт: research/multi_exchange/BACKTESTS/HYP-H16_VALIDATION.md (+ raw output .txt/.json); раннер scripts/run_hyp_h16_validation.py.
- Реестр HYP-H16.yaml: status=REJECTED (VALIDATION_FAIL), добавлен блок results.validation, TRAIN-результаты не изменялись.

**Итог:** HYP-H16 зафиксирована REJECTED без подгонки параметров (последствия D-001). Период 2025-04→2025-10 становится USED. Отрицательный результат сохранён в реестре (negative results policy).

**Следующие задачи (Этап 4–7):**
1. [done] HYP-H16 VALIDATION — FAIL_VALIDATION, REJECTED (см. выше)
2. [in_progress] HYP-M-001: cross-exchange price dislocation study (скачивание klines OKX/KuCoin/HTX/WEEX/BingX + event study)
3. [in_progress] HYP-M-002: cross-sectional momentum на 24 альтах Bybit (TRAIN 2022-11→2025-04)
4. [pending] WS-регистратор funding/OI/ликвидаций (Bybit+OKX) — prospective-данные
5. [pending] Red Team аудит результатов
6. [pending] Архитектура бота + MASTER PROMPT

## 2026-11-08 — Этап 0–3: аудит, исследование, фильтрация (завершено)

**Сделано:**
- Прочитаны docs/RESEARCH_PROTOCOL.md, docs/VALIDATION_PROTOCOL.md; активирован skill trade3-research-protocol.
- Запущены 5 read-only explore-агентов (аудит проекта, аудит OKX/KuCoin/HTX, аудит WEEX/BingX/Bybit, исследование ландшафта стратегий, фильтр идей). Все завершены. Отчёты сохранены в `AGENTS/`.
- Создана структура хранилища research/multi_exchange/.
- Транскрибации автора найдены: experiments/illiquid_spread/reports/transcript_video_A.json (Track A), transcript_video_B.json (Track B). Проверяются как обычные гипотезы.

**Ключевые итоги аудита:**
- 14 REJECTED/FAILS в реестре; единственный PROMISING — HYP-H16 (TSMOM, Sharpe 1.577 TRAIN, валидация не запускалась).
- HYP-A-001: 2 блокера методологии до VALIDATION.
- OOS 2025-10-01→2026-07-01 и HOLDOUT 2026-07-01→2026-10-01 — CONSUMED (HYP-E, объединённый прогон 2025-10→2026-10).
- Единственный крупный чистый период: VALIDATION 2025-04-01→2025-10-01 (1098 H4-баров) — распределён HYP-H16 (решение: DECISIONS/D-001).
- Исторического стакана/ликвидаций нет ни у одной биржи; funding-история обрезана у OKX (~3 мес), WEEX (~6 мес), BingX (~14 мес); klines с 2020 у Bybit/OKX/KuCoin(1d)/HTX/WEEX, BingX только с ~2024-04.
- ТОП-кандидаты: cross-exchange funding carry (только prospective), HYP-H16→VALIDATION, cross-exchange dislocation (klines исторические доступны), cross-sectional momentum Bybit alts, post-liquidation (prospective), Track A (prospective L2).

**Следующие задачи (Этап 4–7):**
1. [done] HYP-H16 VALIDATION (см. раздел Этап 4 выше — FAIL_VALIDATION)
2. [in_progress] HYP-M-001: cross-exchange price dislocation study (скачивание klines OKX/KuCoin/HTX/WEEX/BingX + event study)
3. [done] HYP-M-002: cross-sectional momentum 25 Bybit perps — REJECTED_TRAIN (см. Этап 4 HYP-M-002 ниже)
4. [pending] WS-регистратор funding/OI/ликвидаций (Bybit+OKX) — prospective-данные
5. [pending] Red Team аудит результатов
6. [pending] Архитектура бота + MASTER PROMPT

---

## 2026-11-08 — Этап 4: HYP-M-002 cross-sectional momentum (завершено, REJECTED)

**Сделано:**
- Регистрация ДО прогона: research/registry/HYP-M-002.yaml (сетка L∈{24,48,96}×H∈{4,12}×k∈{3,5}, 12 комбинаций).
- Скрипт scripts/run_hyp_m002_xsmom.py: синхронная close-матрица 5272 бара × 25 символов (inner join), доллар-нейтральный long top-k/short bottom-k, издержки 0.00105/сторона (полный оборот), funding Bybit as-of (конвенция проверена по данным: long платит, short получает), block-bootstrap CI, DSR (N=12).
- Отчёт: research/multi_exchange/BACKTESTS/HYP-M-002_xsmom_train.md, сырые числа hyp_m002_results.json.

**Итог:** REJECTED (TRAIN). Ни одна из 12 комбинаций не проходит: все CI включают 0, DSR ≤ 0.145 (порог 0.95), лучшая (L=24,H=12,k=3: mean +0.085%/период, Sharpe 0.40, PF 1.09) отрицательна при 2× издержках; H=4 устойчиво отрицательны (издержки 0.21%/период > momentum-края); знаки по полугодиям нестабильны (2025-01→04 отрицателен везде). Funding-вклад +2–4% суммарно — несущественен.

**Ограничения:** exploratory/TRAIN-only (независимой валидации нет — confirmatory только на post-2026-10 данных); survivorship bias (25 символов = текущий ликвидный список). Отрицательный результат зафиксирован в реестре, параметры не подгонялись.

---

## 2026-11-09 — Этап 4b: HYP-M-003 funding-спред Bybit↔OKX (exploratory descriptive, DATA_COLLECTION)

**Сделано:**
- Регистрация ДО анализа: research/registry/HYP-M-003.yaml (+HYPOTHESES/HYP-M-003_registration.yaml), статус DATA_COLLECTION, confirmatory-критерии зафиксированы (≥200 меток, 95% CI > 10 bps/8ч, ADF + полувремя < 7 дней, знак ≥ 60%).
- Скрипт scripts/run_hyp_m003_funding_descriptive.py → BACKTESTS/hyp_m003_results.json, отчёт BACKTESTS/HYP-M-003_funding_descriptive.md.
- QC WS-записи: покрытие < 1 суток (11-08 19:35 → 11-09 21:02, разрыв 14.8 ч на перезапуске); **OKX-тикеры не несут funding-полей вообще (0/98k)** — prospective-арм заблокирован до починки регистратора; Bybit funding as-of реконструируется, но редок (13–39 записей/17 ч).
- Отклонение от плана (задокументировано): спред-статистика построена на мосте из публичных REST funding-историй (2026-09 → 2026-11-09, n=181 меток/актив, realized). Сохранено 4 новых датасета: bybit BTCUSDT/ETHUSDT funding 2026-09-10→11-09, okx BTC/ETH-USDT-SWAP funding 2026-09-03→11-09.
- Sanity: REST-мост точно продолжает локальный funding-файл Bybit (5.495e-05 @2026-09-30T16:00); конвенция знака (long платит) подтверждена.

**Итог (exploratory, edge не объявляется):** спред Bybit−OKX суб-бпс: mean abs 0.248 (BTC) / 0.286 (ETH) bps/8ч, p95 ≈ 0.5 bps, **0% меток > 10 bps cost floor за 60 дней**. Ряд стационарен (ADF −5.15/−4.58), полувремя ~0.2 дня, знак нестабилен (53–59%). Против MDPI 2026 (17% наблюдений ≥ 20 bps) — расхождение на порядки; консистентно с REJECTED HYP-M-005 (cross-venue funding dispersion 1.7–2.8 bps/день).

**Вывод:** low prior подтверждён. Ждать 67 дней WS-серии (~2027-01-14) ради подтверждения суб-бпс спреда нерационально. Следующие шаги: (1) починить OKX-источник funding в регистраторе (проверить подписку tickers / поллинг /api/v5/public/funding-rate); (2) опционально HYP-M-006 — историческая проверка Bybit↔OKX↔KuCoin↔HTX на полной глубине (2020→) + ETH/альты (план в отчёте §7), ценность низкая после M-005, оправдана как дешёвый финальный гвоздь.
