# BOT BLUEPRINT — RISK MANAGER (спецификация)

Единственный choke point для всех OrderIntent (`bot/risk/manager.py`). Не bypassable: ни стратегия, ни исполнитель, ни AI не могут обойти (`docs/ARCHITECTURE.md` принцип 3). Default `TRADING_DISABLED=True`; `LIVE_MODE=False` default. Все лимиты — конфиг `bot/config/settings.py` + `venues.yaml`, изменения только через git-коммит (аудируемо).

---

## 1. Иерархия лимитов (каждый Intent проверяется по всем уровням)

| Уровень | Примеры лимитов | Действие при нарушении |
|---|---|---|
| per-strategy | max concurrent positions, max new intents/час, max gross exposure на стратегию, max open risk (% equity) | reject + журнал причины |
| per-venue | max gross exposure на venue, max concurrent orders, max daily notional | reject для venue |
| per-symbol | max exposure на символ через все venue (агрегат, чтобы сумма ног пар не превышала лимит) | reject |
| per-venue-symbol | min_notional/tick/qty по `InstrumentInfo`, ликвидность-фильтр (оборот бара) | reject / уменьшение размера |
| portfolio | total open risk ≤ X% equity, gross ≤ Y%, net delta ≤ Z%, correlation-фильтр (reuse идеи `risk/filters.py` из ARCHITECTURE: correlation, pair-lock) | reject |
| counterparty | остаток средств на venue ≤ лимита (см. §3) | reject + алерт |
| глобальный | TRADING_DISABLED, LIVE_MODE, kill-switch состояния | reject ALL |

Отказ = запись в `audit_log.py` (append-only): intent, нарушенный лимит, значение, лимит, timestamp. Причины reject агрегируются в метрики мониторинга.

## 2. Margin-модель для delta-neutral пар (HYP-M-003 — первый кандидат)

Cross-exchange carry-пара = long перп на A + short тот же перп на B. Ключевое свойство: **маржа требуется на обеих биржах одновременно**, перенос между биржами медленен (вывод/депозит часы–дни).

- **Модель маржи:** isolated margin default на обеих ногах; плечо cap per venue (напр. ≤3× на ногу, конфиг). Не cross-margin: cross на двух независимых venue не существует, а локальный cross между парами смешивает риски.
- **Стресс-маржа:** расчёт занятой маржи при стресс-движении цены на s% против обеих ног одновременно (сбой hedge): required_margin = Σ_legs (notional_leg × (1/L + s) ). При s=10% и L=3 это ~43% notional — лимит портфеля обязан это учитывать: `pair_stress_margin` ≤ лимит.
- **Несбалансированность ног:** если одна нога исполнилась, а вторая отклонена/rejected — позиция становится НЕ delta-neutral. Правило: окно доведения пары ≤ T сек (конфиг, напр. 120 с); по истечении — reduce-only закрытие исполненной ноги (это единственный автоматический reduce-only, разрешённый без kill-switch).
- **Funding-риск:** carry-позиция получает funding, пока открыта, но спред funding может перевернуться (REVERSE спред → carry платит в обе ноги маржи и funding против себя). Лимиты: (а) max hold time на пару (переоценка спреда каждая метка funding); (б) stop-условие: rolling-спред funding за последние N меток < порога → выход по регламенту; (в) funding-издержки учитываются в sizing с запасом (realistic: taker round trip 0.10–0.12%, STRATEGY_IDEAS.md #1).

## 3. Counterparty-лимиты

WEEX — жалобы на вывод средств; BingX — тонкая ликвидность альтов (EXCHANGE_AUDIT_SUMMARY вывод 5).

- `counterparty.max_balance_pct`: остаток средств на venue ≤ X% портфельного equity. Стартовые значения (до калибровки): WEEX ≤ 5%, BingX ≤ 10%, HTX ≤ 15%, KuCoin ≤ 20%, Bybit/OKX ≤ 40% каждая. Конфиг, не константы в коде.
- Проверка: при каждом Intent + периодически (reconciliation). Нарушение → reject новых переводов маржи на venue, алерт; не требует немедленного закрытия позиций (это отдельное решение).
- Правило вывода прибыли (будущее, для live): периодический вывод сверх рабочей маржи с tier-2 venue на tier-1.

## 4. Kill-switch критерии (`bot/risk/kill_switch.py`)

| Критерий | Порог (конфиг) | Реакция |
|---|---|---|
| TRADING_DISABLED | env default True | глобальный reject всех write-операций |
| Portfolio drawdown | от peak equity, напр. −10% день / −25% суммарно | стоп новых входов; алерт; ручное решение о reduce-only |
| Reconciliation divergence | локальное зеркало ≠ venue: позиция-ghost, пропавший close, fee drift > ε | стоп новых входов на venue + алерт; при повторении через 3 цикла — venue halt |
| Venue latency / stall | heartbeat потерян > 30 с, или poll-latency p99 > порог | venue → down; стратегии получают venue_down → NO_TRADE; открытые позиции на venue — только ручные действия |
| Venue error rate | >X% запросов 5xx/timeout за окно | то же, что latency |
| Funding-шок (для carry) | funding-спред разворота за 1 метку > порог | стоп новых carry-пар; переоценка открытых |
| Loss streak per strategy | configurable (паттерн circuit из ARCHITECTURE, injectable clock) | disable стратегии до ручного re-enable |

Каскад реакции всегда: (1) reject новых, (2) cancel resting (reduce-only ордера не трогаем), (3) закрытие позиций — ТОЛЬКО при явном флаге конфига `kill_switch.allow_auto_close=False` default.

## 5. Sizing и ценообразование (интеграция)

- Sizing — fixed-fractional от equity venue-агрегата; из 4 цен (signal/order/fill/avg_fill — политика ARCHITECTURE) SL/TP считаются от `average_fill_price`.
- Волатильность-shutdown: ATR/дневной диапазон > порога → стоп новых входов (паттерн из ARCHITECTURE §Decision Flow).
- Все счётчики (daily loss, drawdown, loss streak) — injectable clock (`bot/core/clock.py`), persisted в `snapshots.db`, чтобы перезапуск не обнулял лимиты.

## 6. Что осознанно не делаем

- Никакого ML-динамического изменения лимитов. Лимиты статичны, меняются только коммитом.
- Никакого обхода для «особых» стратегий. Первая стратегия (M-003) проходит те же ворота.
- Никакой автоматической торговли при расхождении данных между venue > порога (uncertainty = NO_TRADE).
