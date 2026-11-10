# MIGRATION MAP — V3

Date: 2026-09-30  
Rule: nothing migrates without passing an audit gate AND tests.  
Source: `trading-bot/` (v1) and `trading-bot-v2/` (v2) in donor repo.

---

## Classification Legend

| Class | Meaning |
|-------|---------|
| REUSE | Copy with minimal changes after testing |
| REFACTOR | Concept is sound, code must be rewritten |
| RESEARCH_ONLY | Historical data and ideas only, no code copy |
| DO_NOT_USE | Broken, unsafe, or too coupled |

---

## Component Table

| Component | Source | Purpose | Problems | Class | Reason |
|-----------|--------|---------|----------|-------|--------|
| Exchange ABC | v2/exchange/base.py | Exchange abstraction, Position/OrderResult dataclasses | Missing: client_order_id, avg_fill_price, funding, closed_pnl method | REFACTOR | Good contract, needs fields for V3 journal requirements |
| BybitExchange | v2/exchange/bybit.py | Bybit linear perp REST via pybit | Missing: get_closed_pnl, funding rate history, OI history; no idempotency on orders | REFACTOR | Core logic correct, must add missing methods |
| HistoricalExchange (backtest) | v2/backtest/engine.py | Historical data replay for backtest | H4 alignment bug (P1-7); no funding; slippage on exit missing | REFACTOR | Pattern is correct, fix the bugs |
| position sizing (fixed fractional) | v2/risk/sizing.py | Fixed-fractional qty calculation | Correct and pure. No issues. | REUSE | Well-tested pure function, injectable params |
| CircuitBreaker | v2/risk/circuit.py | Daily loss / streak pause | Wall-clock dependency (P0-5) — must become clock-injectable | REFACTOR | Threshold logic is correct; replace `datetime.now()` with injected clock |
| SimulatedCircuitBreaker | v2/backtest/engine.py | Backtest-time CB | Correct for backtest but embedded in engine.py | REFACTOR | Extract to common module; share single implementation with injected clock |
| Journal (SQLite) | v2/data/journal.py | Trade persistence | Missing fee/funding/order_id/fill_price/slippage/R/MAE/MFE (P0-7) | REFACTOR | SQLite structure good, schema must be extended |
| Backtest engine | v2/backtest/engine.py | Bar-by-bar replay | H4 bug, no funding, no exit slippage, per-symbol only | REFACTOR | Architecture is sound (reuses real decision code), fix 3 bugs |
| Backtest fetch/report | v2/backtest/fetch_data.py, report.py | Data download, metrics | fetch: no gap/dedup check. report: thresholds are the right gate. | REFACTOR | Keep threshold gate; add data quality checks |
| Unit tests (v2) | v2/tests/ | 110+ unit tests | No e2e/integration tests | REUSE + EXTEND | Good coverage of pure functions; add integration tests in V3 |
| v1 PostOnly execution | v1/pipeline.py:1644-2042 | PostOnly limit + fallback, avgPrice reconcile | Embedded in 4322-line file; market fallback | RESEARCH_ONLY | The *pattern* (reconcile fill to avgPrice) must be in V3; the code cannot be extracted cleanly |
| Correlation filter / pair-lock | v2/risk/filters.py | Corr-blocked / pair-lock | Not called in v2 backtest (P2) | REFACTOR | Concept correct; must be called in V3 backtest too |
| Bybit fetch_data.py | v2/backtest/fetch_data.py | OHLCV download and cache | No gap/dedup check | REFACTOR | Add strict data quality validation |
| Notifications | v2/notifications/ | Telegram alerts | No issues | REUSE | Clean module, no trading logic |
| config.py patterns | v2/config.py | Typed constants from env | Dead constants (P1-4); TRADING_DISABLED absent (P1-6) | REFACTOR | Pattern (env-loaded, typed) is right; start clean, add only used constants |
| v1 Cascade Confluence signal | v1/pipeline.py:3125-3551 | Gate+score entry logic | Gate/score double counting (P1-1); 4322-line file; no OOS edge | DO_NOT_USE | Failed OOS test; structural double-counting unfixable without rewrite |
| v2 strategy/core.py | v2/strategy/core.py | Simplified entry logic | No proven edge (failed 24-month backtest) | RESEARCH_ONLY | Understand what was tested; do not copy as production strategy |
| v2 strategy/regime.py | v2/strategy/regime.py | Regime classifier | SQUEEZE merges to RANGE (no explicit UNKNOWN=NO_TRADE); thresholds not data-derived | RESEARCH_ONLY | Regime concept correct; thresholds must be researched from data |
| v1 multi-agent AI | v1/multi_agent.py | 4 LLM agents voting BUY/SELL | AI in trade decision path; no calibration; no OOS validation | DO_NOT_USE | Violates V3 AI policy (AI not in entry/exit path) |
| Trailing stop logic | v1/pipeline.py; v2/strategy | Trailing SL after partial close | Own config.py says no-trailing expectancy is better; not independently tested | RESEARCH_ONLY | Research whether trailing adds edge on V3 data before adding |
| Manual probability score | v1/pipeline.py:3329-3428 | 50+10+15=85% "probability" | Not probability; not calibrated; never validated | DO_NOT_USE | Violates V3 probability policy |
| Kelly sizing | v1/pipeline.py:696-773 | Kelly criterion | Dead code — result not read by place_order() | DO_NOT_USE | Misleads about active risk management |
| v1 virtual DEPOSIT=250 | v1/pipeline.py:239 | Sizing base | Not live balance; not documented as active mechanism | DO_NOT_USE | V3 must use live exchange balance |
| SSH hot-patch dashboard | app/api/trading/apply-patch/ | Remote code patch | Bypasses all validation; P0 risk | DO_NOT_USE | Architectural anti-pattern; V3 has no equivalent |
| Champion/Challenger infra | MASTER_PLAN.md references | A/B strategy testing | Status unknown (doc contradiction P1-15); no validation history | DO_NOT_USE until verified | Research Phase only after edge is proven |

---

## Migration Order (after Phase 0 docs complete)

This order is frozen until confirmed by user.

```
1. pyproject.toml / .gitignore / .env.example
   ↓
2. src/trading_engine/common/  — types, errors, time utils, ID generation
   ↓
3. src/trading_engine/config/  — env-loaded typed config (no dead constants)
   ↓
4. src/trading_engine/exchange/base.py  — REFACTOR from v2/exchange/base.py
                                          add: client_order_id, avg_fill_price, get_closed_pnl, funding_rate_history
   ↓
5. src/trading_engine/exchange/bybit/   — REFACTOR from v2/exchange/bybit.py
                                          add: get_closed_pnl, funding_rate_history, OI, idempotency
   ↓
6. src/trading_engine/data/market_data.py  — REFACTOR from v2/backtest/fetch_data.py
                                             add: gap check, dedup, funding/OI ingestion
   ↓
7. src/trading_engine/data/quality.py  — NEW: timestamp ordering, timezone, gaps, warmup, HTF alignment
   ↓
8. src/trading_engine/journal/         — REFACTOR from v2/data/journal.py
                                         add: fee, funding, order_id, fill_price, slippage, R, MAE, MFE, feature_snapshot
   ↓
9. src/trading_engine/risk/sizing.py   — REUSE from v2/risk/sizing.py (tests first)
   ↓
10. src/trading_engine/risk/circuit.py  — REFACTOR: inject clock (abstract TimeSource)
    src/trading_engine/risk/drawdown.py — NEW: live drawdown CB (currently missing P1-5)
    src/trading_engine/risk/kill_switch.py — NEW: TRADING_DISABLED (P1-6)
    ↓
11. src/trading_engine/risk/filters.py  — REFACTOR: correlation, pair-lock (must work in backtest too)
    ↓
12. src/trading_engine/execution/       — REFACTOR v2/execution
                                          enforce: no silent market fallback, reconcile avgPrice always
    ↓
13. src/trading_engine/monitoring/      — REUSE v2/notifications (Telegram)
    ↓
14. src/trading_engine/backtest/        — REFACTOR v2/backtest/engine.py
                                          fix: H4 alignment, funding, exit slippage, portfolio model
    ↓
15. src/trading_engine/research/        — NEW: hypothesis registry, experiment tracking
    ↓
16. ONLY THEN: strategy research (Phase 7)
```

---

## What V3 Does NOT Inherit

- Cascade Confluence entry logic (DO_NOT_USE)
- Manual probability scoring (DO_NOT_USE)
- Multi-agent BUY/SELL voting (DO_NOT_USE)
- Kelly sizing (DO_NOT_USE)
- Old regime thresholds (RESEARCH_ONLY — must be derived from data)
- Old SL/TP parameters (RESEARCH_ONLY — must be derived from data)
- Old trailing parameters (RESEARCH_ONLY — must be tested independently)
- SSH hot-patch dashboard (DO_NOT_USE)
- Virtual DEPOSIT constant (DO_NOT_USE)
