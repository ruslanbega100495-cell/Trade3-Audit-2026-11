# BOT BLUEPRINT — ARCHITECTURE (мультибиржевой торговый бот, 6 venue)

Дата: 2026-11-09. Статус: проект (proposal), не утверждено к реализации.
Автор: Агент-8 (Lead Architect). Scope: проектирование, read-only к существующему коду.

---

## 0. Исходные ограничения (неизменны)

1. `TRADING_DISABLED = True` — default; любой write-path проходит через kill-switch (`docs/ARCHITECTURE.md`, принцип 5, 12).
2. Ни одной подтверждённой стратегии нет (H16 REJECTED, M-002 REJECTED_TRAIN; M-001 в работе). Бот строится как **платформа с пустым портфелем стратегий**; первая кандидатура — HYP-M-003 (funding carry, только после накопления prospective-данных, регистрации в реестре и прохождения протокола).
3. Никаких API-ключей в коде/логах — только env / хранилище секретов (Windows Credential Manager или `.env` вне git; `.env` в gitignore).
4. Binance запрещён. 6 venue: Bybit, OKX, KuCoin, HTX, BingX, WEEX.
5. Вся исследовательская методология (`docs/RESEARCH_PROTOCOL.md`, `docs/VALIDATION_PROTOCOL.md`) применяется к стратегиям до допуска в runtime. Бот не обходит `research/edge_filter`/`validation.py`.
6. Sync-дизайн: `exchange/base.py` — «All methods are synchronous (V3 does not use async)». Это наследуем.

---

## 1. Компонентная схема

```
                    ┌─────────────────────────────────────────────┐
                    │           SUPERVISOR (process monitor)      │
                    │  жизненный цикл workers, restart policy,    │
                    │  global kill-switch, watchdog heartbeat     │
                    └───────┬───────────────────────┬─────────────┘
                            │                       │
        ┌───────────────────▼────┐      ┌───────────▼────────────────┐
        │  VENUE WORKERS × 6     │      │  STRATEGY WORKERS × N      │
        │  (one thread/venue)    │      │  (изолированные, one each) │
        │  bybit/okx/kucoin/htx/ │      │  M-003-carry, ...          │
        │  bingx/weex            │      │  каждая: только читает     │
        │                        │      │  market data, шлёт        │
        │  каждый содержит:      │      │  Intent в risk manager    │
        │  • VenueAdapter (ABC)  │      └───────────┬────────────────┘
        │  • RateLimiter         │                  │ OrderIntent
        │  • ReconciliationLoop  │                  ▼
        │  • Heartbeat→Health    │      ┌───────────────────────────┐
        └───────┬────────────────┘      │  PORTFOLIO RISK MANAGER   │
                │ raw/normalized        │  (единственный choke point)│
                ▼                       │  • per-strategy limits      │
        ┌───────────────┐               │  • per-venue limits         │
        │ NORMALIZATION │               │  • per-symbol exposure      │
        │ venue-agnostic│               │  • portfolio caps           │
        │ → exchange/   │               │  • margin model (pairs)     │
        │   models.py   │               │  • counterparty caps        │
        └───────┬───────┘               │  • kill-switch (drawdown,   │
                │                       │    recon-divergence, lag)   │
     ┌──────────▼──────────┐            │  TRADING_DISABLED default   │
     │  STORAGE            │            └───────────┬─────────────────┘
     │  raw: immutable,    │                        │ OrderPlan (approved)
     │  hash-versioned     │                        ▼
     │  (data/storage.py)  │            ┌───────────────────────────┐
     │  normalized: QC-    │            │  EXECUTION ROUTER         │
     │  checked            │            │  • idempotency keys       │
     │  runtime state:     │            │    (common/id_gen.py)     │
     │  SQLite (journal)   │            │  • venue routing          │
     └──────────┬──────────┘            │  • order state machine    │
                │                       │  • fill tracking          │
     ┌──────────▼──────────┐            │  • reconcile w/ venue     │
     │  MONITORING/ALERTS  │            │    (ghost/missing/fee drift)│
     │  Telegram, health,  │            └───────────┬─────────────────┘
     │  kill-switch panel  │                        │ fills
     └─────────────────────┘            ┌───────────▼───────────────┐
                                        │  JOURNAL (SQLite)         │
                                        │  4 цены, R, MAE/MFE,      │
                                        │  funding, exit_reason,    │
                                        │  strategy_version         │
                                        └───────────────────────────┘
```

Research-контур (backtest/engine.py, walk_forward, holdout, statistics, robustness, validation, regime/) — **отдельный, существующий**, бот его не дублирует и не содержит. Стратегия допускается в runtime только после прохождения протокола; допуск = запись в реестре (research/registry/HYP-*.yaml, status=VALIDATED) + явный whitelist-конфиг.

---

## 2. Компоненты: существующее vs новое

### 2.1 Venue adapters — НОВОЕ (6 штук), но наследники СУЩЕСТВУЮЩЕГО `trading_engine/exchange/base.py`

- `Exchange` ABC (`exchange/base.py`) — контракт уже venue-агностичен: `get_balance`, `get_instrument_info`, `get_klines`, `get_funding_history`, `get_open_interest`, `get_positions`, `get_order`, `get_executions`, `get_closed_pnl`, `create_order`, `cancel_order`, `poll_order`. Нормализованные модели в `exchange/models.py` (Decimal, UTC-aware) переиспользуются как есть.
- Существующий `exchange/bybit.py` (pybit V5) — референс-реализация; в боте переносится как `BybitAdapter` без изменения семантики.
- НОВОЕ для каждой из 5 остальных: thin HTTP-клиент (requests, sync) + нормализация ответов → модели `exchange/models.py`. Детали — `EXCHANGE_ADAPTERS.md`.
- Наследник `HistoricalExchange` (backtest-адаптер) остаётся в research-контуре, в бот не входит.

### 2.2 Normalization — переиспользование + тонкий новый слой

- Существующее: `exchange/models.py` (KlineBar, FundingRate, OpenInterest, OrderDetail, PositionInfo, WalletBalance, Execution, ClosedPnlRecord, InstrumentInfo), `data/quality.py` (gap/dedup/HTF-alignment), `data/alignment.py`.
- НОВОЕ: `bot/normalize.py` — venue-specific парсеры ответов в модели выше (venue → normalized), плюс venue-symbol mapping (`BTC-USDT-SWAP` → `BTCUSDT` и обратно; конфиг-таблица в `bot/config/symbols.yaml`).

### 2.3 Storage — две зоны, разные гарантии

- Research storage: существующее `data/storage.py` + `data/models.py` (DatasetMeta, content hash, immutable raw). Бот сюда **только пишет raw-снимки** (опционально), читает датасеты для воспроизводимости.
- Runtime storage: НОВОЕ `bot/state/` — SQLite:
  - `orders.db` — order state machine (intents, plans, venue order ids, idempotency keys);
  - `positions.db` — локальное зеркало позиций (реконсиляция с venue = source of truth);
  - `snapshots.db` — периодические снапшоты состояния для восстановления после перезапуска.
- Журнал сделок: существующее `journal/store.py` + `journal/models.py` расширяются полями venue (столбец `venue` — новая миграция схемы).

### 2.4 Research-контур — СУЩЕСТВУЮЩИЙ, без изменений

`backtest/{engine,execution}.py`, `research/{registry,splits,walk_forward,holdout,statistics,robustness,validation}.py`, `research/regime/`, `research/hypotheses/`. Бот = потребитель результатов: strategy-runtime читает whitelist из реестра, сам backtest-код в боте не дублируется.

### 2.5 Strategy-runtime — НОВОЕ

- `bot/strategies/base.py` — `Strategy` ABC: `on_bar(ctx) -> list[OrderIntent] | NO_TRADE`; контекст содержит нормализованные бары по всем venue, funding-спреды, режим. Изоляция: каждая стратегия — отдельный worker-процесс/поток с собственным журналом сигналов; исключение в одной не роняет остальные (supervisor restart policy: max 3 рестарта/час, далее — disable + алерт).
- Стратегия **никогда не видит ключи и не вызывает venue API напрямую** — только Intents → Risk Manager.
- Модуль-стратегия читается из конфига по имени; гипотеза ↔ модуль связаны через `hypothesis_id` в реестре; runtime проверяет статус VALIDATED.

### 2.6 Portfolio Risk Manager — НОВОЕ (спецификация в `RISK_MANAGER.md`)

Единственная точка, через которую проходят все OrderIntent. Не bypassable (принцип 3 ARCHITECTURE.md). Содержит: лимиты per-strategy/per-venue/per-symbol/portfolio, margin-модель для delta-neutral пар, counterparty-лимиты, kill-switch. Sync, in-memory + персистентный счётчик в `snapshots.db`.

### 2.7 Execution Router — НОВОЕ

- Принимает только OrderPlan, одобренный Risk Manager.
- Idempotency: `common/id_gen.py` генерирует `client_order_id` (≤36 симв., уникальный per venue per day); ключ детерминирован из `(strategy_id, symbol, venue, bar_time, leg)` — retry после сбоя не создаёт дубль. DuplicateOrderError от venue → сверка с локальным состоянием, не повторная отправка.
- PostOnly limit по умолчанию; market-только под явным флагом конфига (принцип 7).
- Reconciliation loop per venue: каждые N сек сверка open orders/positions с venue; расхождение → алерт + kill-switch критерий.

### 2.8 Мониторинг / алерты / аварийное отключение — НОВОЕ

- `bot/monitoring/`: heartbeat каждого worker (TTL 30 c → считаем venue/strategy down), Telegram-алерты (open/close/error/kill-switch/drawdown), health-endpoint (локальный HTTP на 127.0.0.1) для внешнего watchdog.
- Kill-switch реакции (каскад): (1) стоп новых входов; (2) отмена незаполненных заявок; (3) опционально reduce-only закрытие — только под явным флагом конфига, default: не закрывать (ручное решение).

### 2.9 State recovery — НОВОЕ

При старте: загрузка последнего снапшота → full reconciliation с каждым venue (open orders, positions, balances) → журнал помечает разрыв → только после чистой сверки worker помечается READY. Никаких предположений о состоянии из памяти.

---

## 3. Потоки данных

1. **Market data:** VenueWorker поллит REST klines/funding (и WS-фиды по мере появления) → normalize → кольцевой буфер в памяти + опционально raw-append в research storage → публикация в Strategy Workers (через thread-safe очередь).
2. **Signal:** Strategy → OrderIntent → Risk Manager (reject → журнал сигнала с причиной; NO_TRADE — валидный и частый выход).
3. **Order:** Risk Manager → OrderPlan → Execution Router → VenueAdapter.create_order → poll/fill events → Fill Tracker → Journal → Risk Manager обновляет exposure.
4. **Control:** Monitoring наблюдает всё; kill-switch сигнал видит Risk Manager (блок новых) и Execution Router (cancel resting).

---

## 4. Изоляция и отказоустойчивость

- Падение VenueAdapter (network/5xx/rate-limit): worker уходит в backoff (exp. backoff, кап 5 мин); другие venue не затронуты; стратегии, зависящие от упавшего venue, получают `venue_down` и обязаны вернуть NO_TRADE (жёсткое правило интерфейса).
- Падение Strategy Worker: supervisor рестартует; состояние стратегии восстанавливается из snapshot; позиции, открытые стратегией, остаются под управлением Risk Manager/Execution Router (владение позицией = `strategy_id` в локальном зеркале, не в памяти стратегии).
- Падение Risk Manager или Execution Router: **глобальный stop** (это fail-safe по замыслу — торговать без риск-менеджера нельзя), cancel resting orders, алерт.
- Все ошибки venue — типизированные (`exchange/errors.py` существует: ExchangeError, OrderNotFoundError, DuplicateOrderError, InsufficientBalanceError — переиспользуем + добавляем RateLimitError, AuthError).

---

## 5. Секреты и конфигурация

- `bot/config/settings.py` — переиспользует паттерн `trading_engine/config/settings.py` (env-loaded typed config): `TRADING_DISABLED`, `LIVE_MODE`, per-venue enable-flags, риск-лимиты, whitelist стратегий.
- Ключи: env-переменные `BYBIT_API_KEY` и т.д. (через `.env`/Credential Manager); адаптер получает уже готовый клиент через фабрику `bot/venues/factory.py`; запрет логирования заголовков — тест-страж (unit-тест сканирует, что секретные поля не попадают в journal/логи).
