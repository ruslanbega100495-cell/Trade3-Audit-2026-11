# BOT BLUEPRINT — DIRECTORY TREE

Новое приложение — отдельный пакет `src/bot/` (runtime), поверх существующей библиотеки `src/trading_engine/` (research + общие модели). Binance не подключается.

```
Trade3/
├── src/
│   ├── trading_engine/                 # СУЩЕСТВУЕТ — библиотека, изменения минимальны
│   │   ├── exchange/
│   │   │   ├── base.py                 # [reuse] Exchange ABC — контракт всех адаптеров
│   │   │   ├── models.py               # [reuse] нормализованные модели (KlineBar, OrderDetail, ...)
│   │   │   ├── errors.py               # [reuse] типизированные исключения (+2 новых, см. ниже)
│   │   │   └── bybit.py                # [migrate] логика адаптера → bot/venues/bybit/ (код не дублируется; импорт из trading_engine сохраняется для research)
│   │   ├── data/
│   │   │   ├── storage.py              # [reuse] raw/normalized storage + content hash (research datasets)
│   │   │   ├── quality.py              # [reuse] gap/dedup/HTF-alignment
│   │   │   ├── alignment.py            # [reuse]
│   │   │   └── models.py               # [reuse] CandleRecord/FundingRecord/OIRecord/DatasetMeta
│   │   ├── backtest/                   # [reuse as-is] research-контур, бот не импортирует
│   │   ├── research/                   # [reuse as-is] registry/splits/walk_forward/holdout/statistics/robustness/validation/regime
│   │   ├── journal/
│   │   │   ├── models.py               # [extend] + поле venue (миграция схемы)
│   │   │   └── store.py                # [extend] те же записи + venue index
│   │   ├── common/
│   │   │   ├── id_gen.py               # [reuse] client_order_id
│   │   │   ├── time_utils.py           # [reuse] bar alignment, UTC
│   │   │   ├── errors.py               # [reuse]
│   │   │   └── types.py                # [reuse] доменные типы
│   │   └── config/settings.py          # [reuse pattern] образец для bot-конфига
│   │
│   └── bot/                            # НОВОЕ — приложение-runtime (пустой портфель стратегий на старте)
│       ├── __init__.py
│       ├── main.py                     # entrypoint: загрузка конфига → snapshot → reconcile → supervisor
│       ├── config/
│       │   ├── settings.py             # env-typed: TRADING_DISABLED, LIVE_MODE, venue flags, риск-лимиты
│       │   ├── venues.yaml             # per-venue: base URL, demo-флаг, rate-limit параметры, символы
│       │   ├── symbols.yaml            # venue-symbol mapping (BTCUSDT ↔ BTC-USDT-SWAP ↔ XBTUSDTM ...)
│       │   └── strategies.yaml         # whitelist: hypothesis_id → модуль, лимиты стратегии
│       ├── normalize.py                # venue-ответы → exchange/models.py (парсеры per venue)
│       ├── venues/
│       │   ├── base_mixin.py           # общий код адаптеров: retry/backoff, rate-limit, polling
│       │   ├── factory.py              # создание адаптера по конфигу (внедряет ключи из env)
│       │   ├── bybit/                  # client.py, market_data.py, orders.py, positions.py, funding.py
│       │   ├── okx/                    # + demo-флаг x-simulated-trading
│       │   ├── kucoin/
│       │   ├── htx/
│       │   ├── bingx/                  # + VST-baseURL
│       │   └── weex/                   # historyKlines-особенности, depth 15/200
│       ├── core/
│       │   ├── supervisor.py           # lifecycle workers, restart policy, watchdog
│       │   ├── venue_worker.py         # поток per venue: poll → normalize → buffer → heartbeat
│       │   ├── health.py               # TTL-таблица живости, health-endpoint 127.0.0.1
│       │   └── clock.py                # WallClockTimeSource (паттерн из ARCHITECTURE.md)
│       ├── strategy/
│       │   ├── base.py                 # Strategy ABC: on_bar(ctx) -> intents | NO_TRADE
│       │   ├── context.py              # мультивеню-бары, funding-спреды, режим, venue_down
│       │   ├── worker.py               # поток per strategy, изоляция исключений
│       │   └── registry_link.py        # проверка VALIDATED-статуса в research/registry
│       │   # strategies/ появляются ТОЛЬКО после прохождения протокола; первый кандидат:
│       │   # strategies/m003_funding_carry/  (после накопления prospective-данных)
│       ├── risk/
│       │   ├── manager.py              # ЕДИНСТВЕННЫЙ choke point для OrderIntent
│       │   ├── limits.py               # per-strategy/venue/symbol/portfolio лимиты
│       │   ├── margin.py               # margin-модель delta-neutral пар (двойная маржа)
│       │   ├── counterparty.py         # лимиты остатков WEEX/BingX
│       │   └── kill_switch.py          # drawdown / recon-divergence / latency / TRADING_DISABLED
│       ├── execution/
│       │   ├── router.py               # маршрутизация OrderPlan → venue
│       │   ├── idempotency.py          # ключи из common/id_gen + дедуп локальный
│       │   ├── order_state.py          # state machine per order
│       │   ├── fill_tracker.py         # partial fills, avg_fill (4-цена политика)
│       │   └── reconciliation.py       # per-venue loop: orders/positions/balance сверка
│       ├── state/
│       │   ├── orders_db.py            # SQLite: intents/plans/venue-ids
│       │   ├── mirror_db.py            # SQLite: локальное зеркало позиций
│       │   └── snapshot.py             # периодические снапшоты + восстановление при старте
│       ├── monitoring/
│       │   ├── alerts.py               # Telegram (паттерн v2, новый код)
│       │   ├── metrics.py              # счётчики: fills/min, reject reasons, recon-divergence
│       │   └── audit_log.py            # append-only лог решений риск-менеджера
│       └── secrets/
│           └── loader.py               # env / Windows Credential Manager; никогда не логирует значения
│
├── scripts/
│   ├── start_bot.py                    # НОВОЕ: обёртка запуска (сейчас: only paper)
│   ├── botctl.py                       # НОВОЕ: статус/стоп/kill-switch CLI
│   ├── start_ws_recorder.py            # [exists] collectors/ws_recorder.py запускатор
│   └── collect_mx_klines.py            # [exists] мультибиржевой klines-сборщик
│
├── tests/
│   ├── unit/bot/                       # НОВОЕ: адаптеры (fixture-ответы), risk limits, idempotency,
│   │                                   #       recon, state recovery, secret-страж
│   └── integration/bot/                # НОВОЕ: paper-контур против sandbox/demo venue
│
└── research/multi_exchange/BOT_BLUEPRINT/   # этот блюпринт
```

## Переиспользование существующего кода (явный список)

| Модуль trading_engine | Как используется ботом |
|---|---|
| `exchange/base.py` | Родитель всех 6 VenueAdapter; контракт не меняется |
| `exchange/models.py` | Единственные модели данных на границе venue |
| `exchange/errors.py` | + новые `RateLimitError`, `AuthError` (подклассы ExchangeError) |
| `common/id_gen.py` | Idempotency keys |
| `common/time_utils.py` | Бар-выравнивание, UTC |
| `data/quality.py`, `data/alignment.py` | QC normalized-потоков |
| `data/storage.py` | Raw-запись снимков (immutable, hash) |
| `journal/store.py` | Журнал сделок бота (расширение схемы +venue) |
| `config/settings.py` | Паттерн env-конфига |
| `research/*`, `backtest/*` | Бот только читает результаты/whitelist; код не импортирует в runtime-путь |
| `collectors/ws_recorder.py` | Отдельный процесс; бот не зависит от него, читает те же raw-файлы при исследовании |

## Что намеренно НЕ переиспользуется

- `backtest/execution.py` — своя симуляция; бот работает с реальными venue-адаптерами. Для paper-контура пишется `PaperVenueAdapter` (реализация того же ABC с in-memory стаканом-прокси по last price) — это НОВЫЙ код, не реюз бэктест-execution.
- `research/hypotheses/*` — исследовательские раннеры, не продакшн-модули.
