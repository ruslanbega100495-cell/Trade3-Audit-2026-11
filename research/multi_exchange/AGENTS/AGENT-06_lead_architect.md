# AGENT-06 — LEAD ARCHITECT: blueprint мультибиржевого бота

Дата: 2026-11-09. Тип: coder (read-only к существующему коду). Инструменты: Read по src/trading_engine, docs, research/multi_exchange; написал 5 документов в BOT_BLUEPRINT/.

## Задача
Спроектировать бота (6 venue) с учётом: существующей инфраструктуры Trade3, отсутствия подтверждённых стратегий, TRADING_DISABLED, prospective-данных (M-003/M-004).

## Ключевые решения
1. Бот — отдельное приложение `src/bot/`; trading_engine — библиотека; адаптеры наследуют sync-ABC exchange/base.py и модели exchange/models.py без изменения контракта.
2. Портфель стратегий изначально пуст; допуск только при status=VALIDATED в реестре; первый кандидат — HYP-M-003 после накопления данных.
3. Risk Manager — единственный не-bypassable choke point; TRADING_DISABLED default.
4. Изоляция: поток per venue + поток per strategy под supervisor; venue_down → NO_TRADE; падение Risk/Execution = глобальный fail-safe.
5. Idempotency: детерминированные client_order_id + дедупликация; reconciliation loop → kill-switch критерии.
6. Delta-neutral пары: isolated margin обеих ног, стресс-маржа, таймаут доведения пары, funding-стоп.
7. Counterparty-лимиты: WEEX ≤5% / BingX ≤10% / HTX ≤15% equity (конфиг).
8. Paper-контур — новый PaperVenueAdapter, намеренно не reuse backtest/execution.py.

## Порядок адаптеров
Bybit → OKX (demo, критичен для M-003) → KuCoin → HTX → BingX (VST) → WEEX (последний).

## Главные риски (честная фиксация)
OKX-signer и rate limits HTX/WEEX/KuCoin не извлечены (⚠ в таблице); комиссии WEEX не подтверждены; demo ≠ live; статистика M-003 неделя — незрелая; HTX/WEEX/KuCoin без demo → разрыв paper/live.

## Созданные файлы
ARCHITECTURE.md (152 строк), DIRECTORY_TREE.md, EXCHANGE_ADAPTERS.md, RISK_MANAGER.md, ROADMAP.md (13 этапов, live-gate из 7 условий).

## Ограничения
Проект (proposal), не утверждён к реализации; числа лимитов — конфиг-предложения, требуют проверки при реализации.
