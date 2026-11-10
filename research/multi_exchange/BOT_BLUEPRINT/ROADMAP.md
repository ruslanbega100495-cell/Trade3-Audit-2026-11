# BOT BLUEPRINT — ROADMAP (13 этапов)

Направление: архитектура → адаптеры → данные → хранилище → стратегии → риск → исполнение → мониторинг → тесты → paper → demo → live-gate.
Общие правила: каждый этап закрывается критерием готовности и обновлением `research/multi_exchange/PROGRESS.md`; TRADING_DISABLED=True на всех этапах 1–10; demo (этап 11) и live (этап 13) — только после отдельного разрешения пользователя; портфель стратегий на этапах 1–11 пуст — бот торгует «вхолостую» (paper), что валидно: NO_TRADE — частый и легальный выход.

---

## Этап 1 — Архитектура и скелет
- **Файлы:** `src/bot/` (весь скелет из DIRECTORY_TREE, пустые реализации-заглушки), `bot/config/*`, `bot/main.py`, `bot/core/supervisor.py`, `bot/core/clock.py`.
- **Зависимости:** утверждение этого блюпринта.
- **Критерий готовности:** `main.py` стартует, читает конфиг, корректно падает с TRADING_DISABLED при любой попытке write; структура импортируется без ошибок; unit-тест конфига.
- **Риски:** раздувание скелета без поведения — держать заглушки минимальными.

## Этап 2 — Venue-адаптеры, часть 1: Bybit + OKX
- **Файлы:** `bot/venues/base_mixin.py`, `bot/venues/factory.py`, `bot/venues/bybit/*`, `bot/venues/okx/*` (signer, client), `bot/normalize.py`.
- **Зависимости:** этап 1; `exchange/base.py`, `exchange/models.py` (reuse).
- **Критерий готовности:** read-path (balance/klines/funding/positions) в unit-тестах на fixture-ответах + один integration-прогон против публичных API; OKX demo-флаг в конфиге (не включён по умолчанию).
- **Риски:** OKX подпись v5 (свой signer) — тест на известном векторе; ⚠️ комиссии VIP0 подтвердить перед расчётом издержек.

## Этап 3 — Venue-адаптеры, часть 2: KuCoin + HTX
- **Файлы:** `bot/venues/kucoin/*`, `bot/venues/htx/*`.
- **Зависимости:** этап 2 (паттерны signer/mixin готовы).
- **Критерий готовности:** те же тесты; фиксация ⚠ rate limits HTX (консервативный троттлинг 2 req/s + наблюдение).
- **Риски:** весовые лимиты KuCoin — только эмпирически; HTX demo нет — write-path проверяется только в paper (этап 10) и позже в demo/live-gate.

## Этап 4 — Venue-адаптеры, часть 3: BingX + WEEX
- **Файлы:** `bot/venues/bingx/*` (v2/v3), `bot/venues/weex/*`.
- **Зависимости:** этап 3.
- **Критерий готовности:** те же тесты; WEEX historyKlines-пара start+end покрыта тестом; BingX VST base URL в конфиге.
- **Риски:** WEEX ⚠ комиссии — до подтверждения расчёт издержек консервативный; у обеих слабые исторические данные — не влияет на runtime, влияет на бэктесты этих venue.

## Этап 5 — Поток данных: Venue Workers + нормализация + QC
- **Файлы:** `bot/core/venue_worker.py`, `bot/core/health.py`, интеграция `data/quality.py`.
- **Зависимости:** адаптеры этапов 2–4 (можно по мере готовности).
- **Критерий готовности:** 6 venue (или включённых) поллются по конфигу, heartbeat-таблица живости корректно помечает down-venue; падение адаптера одного venue не роняет остальные (fault-injection тест).
- **Риски:** rate-limit конфликты при 6 поллерах — token-bucket конфиг проверить нагрузочным тестом против публичных API с малым числом символов.

## Этап 6 — Хранилище runtime: state, зеркала, снапшоты
- **Файлы:** `bot/state/orders_db.py`, `bot/state/mirror_db.py`, `bot/state/snapshot.py`; миграция `journal/` (+venue).
- **Зависимости:** этап 5.
- **Критерий готовности:** снапшот→восстановление round-trip тест; журнал пишет с venue; raw-снимки опционально в `data/storage.py` (hash-verified).
- **Риски:** миграция journal-схемы — версионировать, не ломать существующие исследовательские записи.

## Этап 7 — Strategy-runtime (пустой портфель)
- **Файлы:** `bot/strategy/base.py`, `context.py`, `worker.py`, `registry_link.py`.
- **Зависимости:** этап 5 (данные в контексте).
- **Критерий готовности:** пустой whitelist → бот живёт, ничего не торгует; mock-стратегия в тестах генерирует Intents; проверка VALIDATED-статуса из реестра (невалидная гипотеза → runtime-отказ регистрации, тест).
- **Риски:** не написать «первую стратегию» здесь — сознательно; кандидат только из реестра.

## Этап 8 — Risk Manager
- **Файлы:** `bot/risk/*` (manager, limits, margin, counterparty, kill_switch), `bot/monitoring/audit_log.py`.
- **Зависимости:** этап 6 (счётчики persisted), этап 7 (Intents).
- **Критерий готовности:** все лимиты из RISK_MANAGER.md §1–§4 покрыты тестами (reject-пути, kill-switch каскад, margin-модель пары, несбалансированная нога → reduce-only по таймауту); injectable clock; audit log append-only.
- **Риски:** самый критичный модуль — отдельный review + Red Team прогон тестов.

## Этап 9 — Execution Router: idempotency, fills, reconciliation
- **Файлы:** `bot/execution/*`.
- **Зависимости:** этап 8 (OrderPlan only от risk).
- **Критерий готовности:** idempotency-key детерминизм (retry не дублирует); DuplicateOrderError-обработка; fill-tracking 4-цена политика; recon-loop детектит ghost/missing/fee-drift (симуляция в тестах).
- **Риски:** race create→poll — паттерн poll_order из base.py покрывает; тестировать.

## Этап 10 — Мониторинг + тесты + Paper-контур
- **Файлы:** `bot/monitoring/*`, `scripts/start_bot.py`, `scripts/botctl.py`, `tests/unit/bot/**`, `tests/integration/bot/**`; `PaperVenueAdapter` (in-memory исполнение по last price, тот же ABC).
- **Зависимости:** этапы 5–9.
- **Критерий готовности:** paper-бот крутится N дней на всех 6 venue: heartbeat зелёный, recon чистый, журнал полон NO_TRADE/reject-записей, алерты работают; coverage ключевых модулей ≥85% (risk/execution/state).
- **Риски:** PaperVenueAdapter — НЕ бэктест-execution (намеренно); его проскальзывание = 0, это известное ограничение paper.
- **Особенность HTX/WEEX/KuCoin:** demo нет → paper через PaperVenueAdapter с реальными рыночными данными этих venue.

## Этап 11 — Demo-торговля (после отдельного разрешения)
- **Файлы:** конфиг-флаги demo-режима per venue; integration-тесты round-trip.
- **Зависимости:** этап 10; **первая стратегия с VALIDATED-статусом в реестре** (иначе demo нечему торговать — пустой портфель допустим и здесь).
- **Поддержка:** OKX simulated (`x-simulated-trading`), BingX VST, Bybit demo trading. HTX/WEEX/KuCoin — не поддерживают demo → только paper-контур (этап 10) и прямой переход к live-gate позже.
- **Критерий готовности:** на demo-venue пройден полный цикл signal→risk→order→fill→journal→reconcile с реальными demo-ордерами; издержки/комиссии в журнале совпадают с заявленными venue в пределах ε.
- **Риски:** demo ≠ live (исполнение/ликвидность) — demo-результаты не считаются подтверждением edge; недопонимание demo-флагов у OKX (заголовок) — тест, что demo-ордер не уходит в mainnet.

## Этап 12 — Первая стратегия: HYP-M-003 funding carry (исследовательский трек, параллельный этапам 10–11)
- **Зависимости:** накопление prospective-данных WS-регистратором (funding-спреды Bybit↔OKX, недели записи), затем регистрация HYP-M-003 в research/registry, затем протокол TRAIN→VALID→(post-2026-10 holdout). Без VALIDATED — в runtime не допускается (этап 7 регистрация откажет).
- **Критерий готовности:** статус VALIDATED в реестре + модуль `bot/strategy/strategies/m003_funding_carry/` + лимиты пары (margin-модель §2 RISK_MANAGER) в конфиге.
- **Риски:** данных мало (~неделя) — выводы только после статистически значимой выборки; funding-история обрезана у 4 из 6 venue (OKX ~3 мес, WEEX ~6, BingX ~14) — backtest ограничен, опора на prospective + KuCoin/HTX/Bybit полные истории односторонне.

## Этап 13 — Условия допуска к live (go-live gate, жёсткие)
Все условия одновременно:
1. Есть стратегия со статусом VALIDATED в research/registry (на данный момент ни одной — gate закрыт по умолчанию).
2. ≥30 дней demo/paper без reconciliation-divergence и без ложных срабатываний kill-switch (ложных = >0 при исправной инфраструктуре).
3. Реальные издержки demo/paper ≤ модельных + 20% (проскальзывание/комиссии).
4. Risk Manager и kill-switch прошли Red Team review; audit log полон.
5. Counterparty-лимиты настроены; остатки tier-2 venue (WEEX/BingX) в пределах конфига.
6. Письменное разрешение пользователя + явная установка TRADING_DISABLED=False, LIVE_MODE=True (env на машине, не в репо).
7. План аварийного выхода: порядок ручного закрытия позиций per venue, контакты/статусы venue, порог «всё выводить».

Первый live-scope: минимальный размер, 1 стратегия, tier-1 venue (Bybit/OKX), daily review первые 2 недели.

---

## Критический путь
Этапы 1→2→5→7→8→9→10 — последовательно (ядро платформы). Этапы 3–4 ветвятся от 2. Этап 12 идёт параллельно с 10–11 (зависит от накопления данных, не от кода). Этап 11 требует разрешения; этап 13 — gate без сроков.
