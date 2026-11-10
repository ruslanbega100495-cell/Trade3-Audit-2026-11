# SOURCE REGISTER — источники исследования

Дата: 2026-11-08. Формат: ID | источник | дата | рынок | методика | ограничения.

## Академические
- SRC-MEX-01 | Guo, Intini, Jahanshahloo — Bitcoin arbitrage and exchange default risk, Finance Research Letters 71, 2025 | 04/2013–04/2024 | BTC-спот, 16 бирж | минутные данные, panel | не USDT-перпы; до 04/2024
- SRC-MEX-02 | Makarov & Schoar — Limits to Arbitrage (JFE 2020), arXiv:1812.00595 | ≤2018 | кросс-биржевой BTC | сетевые данные + стаканы | старые данные
- SRC-MEX-03 | Two-Tiered Structure of Cryptocurrency Funding Rate Markets, Mathematics (MDPI) 14(2):346 | 2026 (окно 8 суток) | 26 бирж, 749 символов, 1-мин панель | арбитражные спреды funding | окно 8 дней — главное ограничение
- SRC-MEX-04 | Designing funding rates for perpetual futures, arXiv:2506.08573 | 06/2025 | теория перпов | реплицирующие портфели | без эмпирики
- SRC-MOM-01 | AdaptiveTrend — Systematic Trend-Following with Adaptive Portfolio Construction, arXiv:2602.11708 | OOS 2022–2024 | 150+ пар, 6ч | авторский бэктест Sharpe 2.41 | требует репликации
- SRC-MOM-02 | A Decade of Evidence of Trend Following in Cryptocurrencies, arXiv:2009.12155 | 2010-е | крипто-индексы | walkforward | данные до 2020
- SRC-MOM-03 | The Weekend Effect in Crypto Momentum, Advances in Consumer Research | 01/2020–04/2025 | 10 криптовалют | дневные | без модели издержек
- SRC-MR-01 | Short-horizon mean reversion in cryptocurrency markets, arXiv:2608.21888 | 2026 | 183 пары Binance vs 187 акций | strict OOS | gross ~1.3 bp < издержек
- SRC-SA-01 | Dynamic Multi-Pair Trading with DRL, arXiv:2606.04574 | 06/2026 | Binance USD-M, 1ч | иерархический отбор + PPO | bootstrap p≈0.06; одна биржа
- SRC-SA-02 | RL Pair Trading: Dynamic Scaling, arXiv:2407.16103 | 07/2024 | BTC-GBP/EUR 1м | классика 8.33% vs RL до 31.53% год | 2 пары, издержки слабо
- SRC-SA-03 | Dynamic Cointegration-Based Pairs, arXiv:2109.10662 | 09/2021 | крипто | динамическая коинтеграция | данные до 2021
- SRC-LIQ-01 | Measuring the engine of a liquidation cascade, arXiv:2608.03616 | 2022–2025 (7 каскадов, вкл. $19 млрд 10.10.2025) | ликвидации | subcritical branching λ≈0.1–0.2 | анализ механизма, не стратегия
- SRC-LIQ-02 | Where does the criticality live?, arXiv:2607.27070 | 2026 | 7 каскадов, 39 конфигураций | per-event early warning | сигналов тревоги нет (per-event)
- SRC-OF-01 | The Market Maker's Dilemma, arXiv:2502.18625 | 02/2025 | Binance BTC-perp | live-эксперимент | про MM, не прямой сигнал
- SRC-OF-02 | Relaver — Resolving Latency and Inventory Risk in MM with RL, arXiv:2505.12465 | 05/2025 | симуляция | латентности 30–100 мс | симуляция
- SRC-VOL-01 | Multifractality in digital currency markets, arXiv:2510.13785; Probabilistic Forecasting Crypto Volatility, arXiv:2508.15922 | 2025 | крипто RV | предсказуемость RV | прогноз ≠ прибыль
- SRC-REG-01 | Evolutionary correlation, regime switching…, arXiv:2112.15321; Early Detection of Latent Microstructure Regimes, arXiv:2604.20949 | 2021/2026 | крипто/LOB | спектральные/режимные | референсы

## Практические/рыночные
- SRC-PRAC-01 | HFT Advisory — Cross-Exchange Arbitrage and the Crypto OMS Gap | 22.02.2026 | кросс-биржевой | Kaiko-данные, латентности | блог без peer review, частично маркетинг
- SRC-PRAC-02 | CoinGlass Learn — What is Funding Rate Arbitrage | 2024–2025 | funding | механика + пример carry | учебный, бэктеста нет
- SRC-PRAC-03 | PYE Markets — Bitcoin Futures Basis (CME) | 21.10.2026 | CME basis | первичные closes | рассинхрон close
- SRC-PRAC-04 | CoinDesk — BTC futures deepest backwardation since FTX | 03.12.2025 | CME | заголовок/факт | полный текст за чекпоинтом
- SRC-PRAC-05 | Quantpedia — Intraday Seasonality in Bitcoin (Padyšák & Vojtko SSRN) | 2015–2021 | BTC | 22:00 UTC long | издержки не учтены, вероятно затухло
- SRC-PRAC-06 | Reddit r/CryptoExchange / Trustpilot — жалобы на вывод WEEX | 2024 | WEEX | анекдоты | самоотбор негатива; для риск-лимитов релевантно
- SRC-PRAC-07 | CoinCarp WEEX review | 2024–2025 | WEEX | статус лицензий | факты без арбитражных данных

## Документация бирж (проверено 2026-11-08)
- Bybit V5: bybit-exchange.github.io/docs/v5 (kline, funding/history, open-interest, insurance, WS liquidation)
- OKX v5: okx.com/docs-v5 (history-candles, funding-rate-history, rubik OI, liquidation-orders, demo trading)
- KuCoin: kucoin.com/docs-new (kline/query, contract/funding-rates, level2; fees из /contracts/XBTUSDTM)
- HTX: huobiapi.github.io/docs/usdt_swap/v1 + bulletin 94916436903925 (v1→v3 liquidations); fees: htx.com/support/900000089923
- WEEX: weex.com/api-doc + CCXT weex.ts (historyKlines, fundingRate cap 365d, depth 15/200)
- BingX: bingx-api.github.io/docs-v3 + open-api-vst.bingx.com (VST demo подтверждён)

## Локальные транскрибации автора
- LOC-TR-A | transcript_video_A.json (Video loVcAj_Cgmc, Track A CEX spot spread) | SOURCE_EVIDENCE.md A-01…A-14
- LOC-TR-B | transcript_video_B.json (Video D-zD6uAX19M, Track B DEX perp lag scalping) | SOURCE_EVIDENCE.md B-01…B-14
