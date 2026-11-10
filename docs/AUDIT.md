# PHASE 0 — AUDIT REPORT (V3)

Date: 2026-09-30  
Status: READ-ONLY. No code was written, changed, or copied.  
Scope: `trading-bot/`, `trading-bot-v2/`, all `.md` docs, git history.  
Prior art: `PHASE0_AUDIT_REPORT.md` (2026-09-27) in donor repo — this document extends and references it.

---

## 1. Repository Audit

### 1.1 Donor structure

```
трейдинг новый/
  trading-bot/            v1 live bot — Bybit H1, Cascade Confluence, 4322-line pipeline.py
  trading-bot-v2/         modular rewrite — strategy/risk/execution/exchange/backtest
  MASTER_PLAN.md          evolving plan doc (partially obsolete)
  PLAN-STRATEGY-v2.md     honest OOS-test report — negative result, most important doc
  trading_bot_v2_plan.md  v2 build plan (frozen at fail)
  PHASE0_AUDIT_REPORT.md  prior audit (2026-09-27, comprehensive)
  CHANGES.md              partial changelog of SSH-applied patches
```

### 1.2 V3 structure (current)

```
trading-bot новый -v3/
  TRADING-BOT-V3-MASTER-PLAN.md   principles and lifecycle (good)
  Текстовый документ.txt           (unknown content, not relevant)
  docs/                            (this directory, being created now)
```

### 1.3 Git history key facts

| Commit | Date | Content |
|--------|------|---------|
| 07e487f | latest | AUDIT_REPORT_V3 — auth, risk thresholds, config |
| 518f3e3 | | v2 strategy stopped — failed backtest confirmed |
| 63507f8 | | v2 backtest: 24 months, WR 33.2%, PF 0.76, Sharpe -2.72 |
| 292137b | | v2 Weeks 4-5: OANDA mock, Telegram, main.py |
| 753e240 | | v2 Weeks 2-3: strategy/risk/execution, 92 tests |

Server ↔ git gap: 6 weeks (2026-08-13 → 2026-09-25). Live changes via SSH not committed.

---

## 2. Critical Problems (P0 / P1 / P2)

Full list: `PHASE0_AUDIT_REPORT.md §4`.  
Summarized for V3 migration decisions:

### P0

| # | Problem | Impact on V3 |
|---|---------|--------------|
| P0-1 | No proven edge in any existing strategy (honest OOS: WR 29-33%, PF 0.76) | V3 cannot inherit any strategy. Start from data. |
| P0-2 | `AUDIT_REPORT_V3.md` missing — referenced in 8+ places in pipeline.py and STRATEGY.md | Cannot verify which fixes were actually applied to v1. Assume unknown. |
| P0-3 | Server ↔ git 6-week gap. Live params differ from any documented version | V1 is unknown ground truth. Do not REUSE, only RESEARCH_ONLY. |
| P0-4 | Hot-patch dashboard (`apply-patch/route.ts` → SSH → pipeline.py) bypasses any validation cycle | V3 must have no equivalent mechanism. |
| P0-5 | v2 CircuitBreaker: wall-clock bug silently stopped 24-month backtest for months (SimulatedCB fixes it for backtest only; live `risk/circuit.py` still uses wall-clock) | V3 risk/circuit must be clock-injectable from the start. |
| P0-6 | v2 exchange-driven SL/TP close not reconciled in journal (monitor detects disappearance but doesn't call close_trade()) | V3 journal must handle all exit reasons, including exchange-driven. |
| P0-7 | v2 journal: no fee / order_id / fill_price / slippage / R / MAE / MFE | V3 journal schema defined from the start with all required fields. |
| P0-8 | Funding not modeled anywhere (not in backtest, not in live P&L) | V3 backtest must include funding as cost. |

### P1

| # | Problem | Impact on V3 |
|---|---------|--------------|
| P1-1 | Gate + Score double-counting (VWAP/RSI/MACD/EMA score AND gate) → inflated effective weight | DO_NOT_USE the Cascade Confluence scoring approach. |
| P1-2 | Trailing cuts profits (own config.py comment: no-trailing is better by expectancy) | Research trailing independently. Do not inherit params. |
| P1-3 | v2 limit→market fallback contradicts plan §19.3 ("no market orders") | V3 execution model must be explicit about order type policy. |
| P1-4 | Dead config constants (MAX_DAILY_LOSS_PCT, SIGNAL_COOLDOWN_SEC, etc.) look active but do nothing | V3 config must have no unused constants. |
| P1-5 | v2: no live drawdown circuit breaker (only post-hoc in backtest report) | V3 risk engine must have live drawdown CB. |
| P1-6 | v2: no TRADING_DISABLED kill switch | V3 default: TRADING_DISABLED = True. |
| P1-7 | v2 H4-confirmation: gets unclosed H4 bar in 1-3 of every 4 H1 bars (start <= now_ts, not start+4h <= now_ts) | V3 HTF alignment must be strict: bar is available only after it closes. |
| P1-8 | v1 sizing uses hardcoded DEPOSIT=250, not live balance | V3 must use live exchange balance always. |

### P2

- v1 repo: ~40 .backup/.bak_*/ fix_*.py files mixed with live code.
- v1 tests: assert-scripts, not pytest-discoverable.
- v2: no integration/e2e test of full main.py cycle on synthetic data.
- v2 probability: manual `50 + 10 + 15 = 85%` is NOT probability; not calibrated.

---

## 3. Backtest Correctness Audit (v2)

| Check | Status | Notes |
|-------|--------|-------|
| Lookahead on indicators | OK | iloc[:-1] applied before all indicator reads |
| Closed bars only | OK | get_klines() strips last bar |
| H4 bar alignment | BUG (P1-7) | H4 available at H1[0] of each H4 period, not H1[3] |
| Signal price vs fill price | OK | explicit SLIPPAGE_BUFFER_PCT applied as adverse cost |
| Intrabar SL/TP ambiguity | OK | SL-first rule, deterministic, tested |
| Maker/taker fees | OK | MAKER_FEE entry, TAKER_FEE exit |
| Slippage on exit | MISSING | SL/TP exits at exact price, no adverse slippage |
| Funding | MISSING | 0 grep matches in backtest/ |
| Portfolio model | MISSING | symbols independent; correlation/pair-lock not called |
| Balance evolution | OK | cumulative balance tracked |
| CircuitBreaker clock | FIXED (backtest only) | SimulatedCB correct; live circuit.py still wall-clock |
| Parameter optimization | NONE | fixed constants before run (good) |
| Deterministic | YES | no RNG, reproducible |

---

## 4. Signal/Fill Price Audit

| Component | Signal Price | Fill Price | Separated |
|-----------|-------------|------------|-----------|
| v1 pipeline.py | close of last closed H1 | exchange avgPrice (post-fill reconcile) | YES — v1 does this correctly |
| v2 execution | signal bar close | NOT STORED — journal writes entry_price = signal price | NO — P0-7 |
| v2 backtest | signal bar close | close + SLIPPAGE_BUFFER_PCT (adverse) | YES — correct for backtest |

V3 must have: `signal_price`, `order_price`, `fill_price`, `average_fill_price` as separate fields everywhere.

---

## 5. Funding Audit

| Component | Funding as Gate | Funding as Cost | Funding History |
|-----------|----------------|-----------------|-----------------|
| v1 live | YES (FUNDING_RATE_EXTREME_PCT blocks entry) | NO | NO |
| v2 live | NO | NO | NO |
| v2 backtest | NO | NO | NO |

V3 must model funding as a cost in backtest and track it in journal.

---

## 6. Regime / UNKNOWN State

v1 regimes: TREND, RANGE, SHOCK, SQUEEZE.  
v2 regimes: TREND, RANGE, SHOCK, SQUEEZE (SQUEEZE enabled=False → trades as RANGE).

Problem: v2 SQUEEZE is labeled `enabled=False` but is not distinct from RANGE in practice — it silently merges with RANGE rather than returning UNKNOWN/NO_TRADE.

V3 must have explicit UNKNOWN state that maps to NO_TRADE.  
Regime thresholds must be derived from data, not inherited from v1/v2.

---

## 7. AI / Multi-Agent Audit

v1 multi_agent.py: 4 LLM agents (market analyst, news, risk, portfolio, strategy selector).  
Decision path: score ≥ 80 → bypass AI; otherwise consensus ≥ 3/4 agents required.

Problems:
- Agents can vote BUY/SELL → they ARE in the trade decision path, directly.
- No calibration. "BUY" from LLM has no statistical meaning as probability.
- No OOS test of agent contribution vs random baseline.

V3 AI rule: AI is NOT in the entry/exit decision path. See ARCHITECTURE.md.

---

## 8. Strategy Audit

Both strategies are RESEARCH_ONLY:

| Strategy | Sample | Result | Status |
|----------|--------|--------|--------|
| v1 Cascade Confluence | 2448 trades (PLAN-STRATEGY-v2.md) | WR 29-32.6%, effectively random at R:R | RESEARCH_ONLY |
| v2 Simplified strategy | 24 months walk-forward, 710 trades | WR 33.2%, PF 0.76, Sharpe -2.72, degrading | FAILED gate, RESEARCH_ONLY |

The v2 backtest is the most honest evidence in the project. Its conclusion stands: no proven edge in either strategy.
