# AGENT-01 — DATA ENGINEER: аудит состояния проекта Trade3

Дата: 2026-11-08. Тип: explore (read-only). Инструменты: Read/Glob/Grep по research/registry, research/reports, experiments/illiquid_spread, src/trading_engine, docs.

## Реестр гипотез (18 YAML, research/registry/)
Все — Bybit USDT-перпы, ТФ H4, split TRAIN 2024-01-01→2025-04-01 (HYP-L-001: 2023-01→2024-06-30).

| id | Статус | Суть | Результат (train) |
|---|---|---|---|
| HYP-G-001 | REJECTED | Реверсия после экстремального funding (top/bottom 10% rolling-400), BTC | n=318, все горизонты p=0.21–0.94, нет предиктивности |
| HYP-H-001 | REJECTED | Реверсия после экстремума basis perp/spot, BTC | n=602, dir-return −0.07%…+0.02%, p=0.70–0.999 |
| HYP-H15 | REJECTED | Funding carry BTC timing (short f>+0.008%, long f<−0.005%) | 761 сделка, WR 0.390, Sharpe −4.174, MaxDD 212.6%, PnL −202.5% |
| HYP-H16 | PROMISING | Vol-normalized TSMOM (N=12/24, target_vol 0.20) | Лучший N12 vol-scaled: n=225, Sharpe 1.577, MaxDD 15.9%, +50.5%, WR 0.533. VALIDATION не проводилась |
| HYP-J-001 | REJECTED | MR от экстремумов Bollinger (N=20, k=2) | n=330, AC=−0.034, p=0.46–0.92 |
| HYP-K-001 | REJECTED | MA-кроссовер (20/50, 35/195) | 63 кроссовера, p=0.497/0.913 |
| HYP-K-002 | REJECTED | Liquidity sweep → реверсия | n=285, dir-return отрицательны во всех горизонтах |
| HYP-K-003 | REJECTED | FVG fill (ICT) | n=441, p>0.27, placebo-совместимо |
| HYP-K-004 | REJECTED | ATR-волна ≥80% ATR(14) → реверсия | n=3599, H32 p=0.062, Holm fail |
| HYP-K-005 | REJECTED | Sweep + structure break (AZ-07) | n=183, H32 p=0.032, Holm fail |
| HYP-K-005-BNB/ETH/SOL | FAILS_TO_REJECT | Кросс-символьные репликации | n=166/156/175, генерализации нет |
| HYP-K-006 | REJECTED | Funding экстрем + сжатие OI | n=146, p=0.12–0.67 |
| HYP-K-007 | REJECTED | Абсолютный уровень OI в экстремумах | n=807, t≈0.3; нестационарность OI (34.5% vs 20%) |
| HYP-K-008 | REJECTED | Пробой + падение OI → реверсия | n=225, dir-return отрицательны, p=0.084 |
| HYP-L-001 | REGISTERED (пауза) | Кросс-секциональный funding carry, ~25 перпов, ребаланс 8ч | Данные скачаны, backtest не запускался |

## Израсходованные периоды
HOLDOUT 2026-07-01→2026-10-01 CONSUMED by HYP-E (0/8 positive cells). Фактически израсходован и объединённый 2025-10-01→2026-10-01 (OOS+HOLDOUT). VALIDATION 2025-04-01→2025-10-01 — единственный чистый период (см. PERIOD_MAP.md, D-001).

## Датасеты
research/datasets/raw/bybit/: 24 символа × {H4, funding} 2022-11-01→2025-04-01; BTCUSDT дополнительно H4/OI/spot/funding 2024-01-01→2026-09-30; BNB/ETH вторые H4-файлы. QC: 0 гэпов, 0 дублей. Пробелы: OI/spot только BTC; funding альтов заканчивается 2025-04; нет данных других бирж; нет тиков/L2.

## illiquid_spread — итоги
H1 passive spread REJECTED (−1.295 USDT/228 RT); H2 OFI FALSIFIED (WR 28.7%, avg −10.6 bps); H4-v1 FALSIFIED (WR 20%); H-RS/H-MR NOT_VALIDATED (после исправления look-ahead); H5 INSUFFICIENT_N; H_SPREAD CONFIRMED (AsterDEX BRUSDT спред 0.180% vs Bybit 0.039–0.055%); H_LAG FALSIFIED (median −43 мс, 0/4 блоков). Отвергнуты площадки: MEXC/HTX (делистинг символов), Gate.io (gross-экономика отрицательна).

## Инфраструктура src/trading_engine
Реализовано: exchange/base.py (ABC) + bybit.py; data/{sources,storage,quality,alignment}.py; backtest/{engine,execution}.py; research/{walk_forward,holdout,splits,statistics,robustness,validation,registry}.py; research/regime/; journal/. НЕ реализовано (план в ARCHITECTURE.md): features/, risk/, execution/, strategies/, monitoring/. Нет общего мультибиржевого коллектора.

## Рекомендации
Адаптеры новых бирж — к существующим ABC; backtest/walk-forward/holdout-lock бирженезависимы. Ключевой риск: единственный чистый VALIDATION-период конкурирует между H16 и A-001 (разрешено D-001 в пользу H16).

## Ограничения
Отчёт основан на чтении YAML/отчётов; код гипотез не перечитывался построчно; smart-explore MCP недоступен (использованы Glob/Read).
