"""
STEP 7.3 — Run HYP-A-001 on real Bybit data.

Usage:
    cd "C:\\Users\\rusla\\проект мульти\\trading-bot новый -v3"
    python scripts/run_step_7_3.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from datetime import datetime, timezone
from pathlib import Path
import json

from trading_engine.research.bybit_downloader import download_candles, save_raw_json, load_raw_json
from trading_engine.research.splits import make_splits, filter_by_split, SPLIT_BOUNDARIES
from trading_engine.research.hypotheses.hyp_a_001 import (
    make_hypothesis, make_parameter_snapshot, LOOKBACK, HORIZONS,
    HYP_A_001_ID, CODE_VERSION,
)
from trading_engine.research.hypotheses.study_runner import HypAStudyRunner
from trading_engine.research.registry import HypothesisRegistry
from trading_engine.research.results import ResultsStore
from trading_engine.research.models import SplitType
from trading_engine.data.quality import DataValidator

_UTC = timezone.utc
DATASETS_DIR = Path(__file__).parent.parent / "research" / "datasets"
DOCS_DIR = Path(__file__).parent.parent / "docs" / "research"
DOCS_DIR.mkdir(parents=True, exist_ok=True)
DATASETS_DIR.mkdir(parents=True, exist_ok=True)

SYMBOL = "BTCUSDT"
TIMEFRAME = "H4"
DATASET_ID = f"{SYMBOL}-{TIMEFRAME}-2024-2026"


def main():
    print("=" * 60)
    print("STEP 7.3 — HYP-A-001 REAL DATA PIPELINE")
    print("=" * 60)

    # ── 1. Download ──────────────────────────────────────────────
    print("\n[1] Downloading BTCUSDT H4 from Bybit...")
    start = SPLIT_BOUNDARIES["train_start"]
    end = SPLIT_BOUNDARIES["holdout_end"]

    # Check if we already have a saved dataset
    raw_dir = DATASETS_DIR / "raw" / "bybit" / SYMBOL / TIMEFRAME
    existing = list(raw_dir.glob("*.json")) if raw_dir.exists() else []

    if existing:
        latest = sorted(existing)[-1]
        print(f"  Found existing dataset: {latest.name}")
        with open(latest) as f:
            meta = json.load(f)
        cached_start = datetime.fromisoformat(meta["start"])
        if cached_start.tzinfo is None:
            cached_start = cached_start.replace(tzinfo=_UTC)
        # Validate: cache must cover at least the TRAIN start
        if cached_start <= SPLIT_BOUNDARIES["train_start"]:
            print(f"  Loading from cache (covers from {cached_start.date()})...")
            candles = load_raw_json(latest)
            dataset_hash = meta["dataset_hash"]
            print(f"  Loaded {len(candles)} candles, hash={dataset_hash[:16]}")
            result = None
        else:
            print(f"  Cache is stale (starts {cached_start.date()}, need {SPLIT_BOUNDARIES['train_start'].date()}). Re-downloading...")
            existing = []  # force re-download path below

    if not existing:
        result = download_candles(SYMBOL, TIMEFRAME, start, end)

        if not result.success:
            print(f"\n  DATA SOURCE FAILURE")
            print(f"  Symbol:     {SYMBOL}")
            print(f"  Timeframe:  {TIMEFRAME}")
            print(f"  Period:     {start.date()} → {end.date()}")
            print(f"  Error:      {result.error}")
            print(f"\n  Next required action: Check network / Bybit API status and retry.")
            sys.exit(1)

        candles = result.candles
        dataset_hash = result.dataset_hash
        print(f"  Downloaded {result.raw_count} raw candles")
        print(f"  Valid candles: {len(candles)}")
        print(f"  Duplicates removed: {result.duplicates_removed}")
        print(f"  Invalid removed: {result.invalid_removed}")
        print(f"  Dataset hash: {dataset_hash}")

        # Save raw JSON
        saved_path = save_raw_json(result, DATASETS_DIR)
        print(f"  Saved to: {saved_path}")

    if not candles:
        print("\n  DATA GAP")
        print(f"  Required: {start.date()} → {end.date()} BTCUSDT H4")
        print(f"  Available: 0 candles")
        print(f"  Missing: complete dataset")
        sys.exit(1)

    # ── 2. Data quality report ──────────────────────────────────
    print("\n[2] Data quality check...")
    validator = DataValidator()
    issues = validator.validate_candles(candles, check_gaps=True)
    issue_counts = {}
    for qi in issues:
        t = qi.issue_type.value
        issue_counts[t] = issue_counts.get(t, 0) + 1
    print(f"  Total candles: {len(candles)}")
    print(f"  Issues found: {len(issues)}")
    for t, n in sorted(issue_counts.items()):
        print(f"    {t}: {n}")

    # ── 3. Splits ────────────────────────────────────────────────
    print("\n[3] Creating data splits...")
    splits = make_splits(DATASET_ID, dataset_hash)
    for name, split in splits.items():
        split_candles = filter_by_split(candles, split)
        print(f"  {name.upper():12s}: {split.start.date()} → {split.end.date()} = {len(split_candles)} candles")

    train_candles = filter_by_split(candles, splits["train"])
    if len(train_candles) < LOOKBACK + max(HORIZONS) + 10:
        print(f"\n  DATA GAP: TRAIN split has only {len(train_candles)} candles (need >{LOOKBACK + max(HORIZONS) + 10})")
        sys.exit(1)

    # ── 4. Register HYP-A-001 ───────────────────────────────────
    print("\n[4] Registering HYP-A-001...")
    registry = HypothesisRegistry()
    results_store = ResultsStore()
    hyp = make_hypothesis(DATASET_ID)
    registered = registry.register(hyp)
    print(f"  Status: {registered.status.value}")
    print(f"  Lookback: {LOOKBACK}  Horizons: {HORIZONS}")
    print(f"  Code version: {CODE_VERSION}")

    # ── 5. Run event study on TRAIN ─────────────────────────────
    print("\n[5] Running HYP-A-001 event study on TRAIN split...")
    runner = HypAStudyRunner(registry=registry, results_store=results_store)
    train_report = runner.run(
        candles=train_candles,
        dataset_id=DATASET_ID,
        dataset_hash=dataset_hash,
        split=splits["train"],
        run_walk_forward=True,
        run_cost_stress=True,
        wf_train_bars=300,
        wf_test_bars=100,
    )
    print(f"  Status: {train_report.status}")
    print(f"  Long events: {train_report.long_event_count}")
    print(f"  Short events: {train_report.short_event_count}")
    print(f"  Edge evaluation: {train_report.final_verdict}")

    # ── 6. Print per-horizon results ────────────────────────────
    print("\n[6] Forward return results (TRAIN split):")
    for h in HORIZONS:
        lr = train_report.long_gross.get(h)
        sr = train_report.short_gross.get(h)
        bl = train_report.baseline_a.get(h)
        lm = f"{float(lr.mean_return):.4f}" if lr and lr.mean_return else "N/A"
        lw = f"{lr.win_rate:.2f}" if lr and lr.win_rate else "N/A"
        sm = f"{float(sr.mean_return):.4f}" if sr and sr.mean_return else "N/A"
        sw = f"{sr.win_rate:.2f}" if sr and sr.win_rate else "N/A"
        bm = f"{float(bl.mean_return):.4f}" if bl and bl.mean_return else "N/A"
        print(f"  H{h:>2}: Long mean={lm} wr={lw} | Short mean={sm} wr={sw} | Base={bm}")

    # ── 7. Walk-forward ─────────────────────────────────────────
    wfr = train_report.walk_forward_result
    if wfr:
        print(f"\n[7] Walk-forward: {wfr.total_windows} windows, {wfr.completed_windows} completed")
        print(f"  Window win rate: {wfr.window_win_rate:.2f} ({wfr.profitable_windows}/{wfr.completed_windows})")

    # ── 8. Robustness ───────────────────────────────────────────
    csr = train_report.cost_stress_report
    if csr:
        print(f"\n[8] Cost robustness:")
        for r in csr.results:
            survives = "OK" if r.metrics and r.metrics.net_pnl >= 0 else "NEGATIVE"
            print(f"  {r.cost_multiplier:.2f}x: {survives}")

    print(f"\n[9] Final verdict: {train_report.final_verdict}")

    # ── 9. Write report ─────────────────────────────────────────
    _write_report(
        report=train_report,
        candles=candles,
        train_candles=train_candles,
        splits=splits,
        issues=issues,
        issue_counts=issue_counts,
        dataset_hash=dataset_hash,
        result=result,
    )
    print(f"\n  Report saved to: docs/research/HYP-A-001_REAL_DATA_REPORT.md")
    print("\nDONE. STOP — awaiting confirmation before next step.")


def _write_report(report, candles, train_candles, splits, issues, issue_counts,
                  dataset_hash, result):
    from trading_engine.research.hypotheses.hyp_a_001 import (
        LOOKBACK, HORIZONS, HYP_A_001_ID, CODE_VERSION, TAKER_FEE_RATE, SLIPPAGE_RATE
    )

    lines = ["# HYP-A-001 — REAL DATA REPORT", ""]
    lines += ["## Dataset", f"Source: Bybit public API (linear perpetuals)",
              f"Symbol: BTCUSDT", f"Timeframe: H4",
              f"Period: {candles[0].open_time.date()} → {candles[-1].close_time.date()}",
              f"Records: {len(candles)}",
              f"Dataset hash: {dataset_hash}", ""]

    lines += ["## Data Quality"]
    lines.append(f"Total candles: {len(candles)}")
    lines.append(f"Duplicate candles removed: {result.duplicates_removed if result else 'N/A (from cache)'}")
    lines.append(f"Invalid OHLC removed: {result.invalid_removed if result else 'N/A (from cache)'}")
    lines.append(f"Quality issues found: {len(issues)}")
    for t, n in sorted(issue_counts.items()):
        lines.append(f"  {t}: {n}")
    lines.append("")

    lines += ["## Splits"]
    for name, split in splits.items():
        sc = [c for c in candles if split.start <= c.open_time < split.end]
        lines.append(f"{name.upper()}: {split.start.date()} → {split.end.date()} = {len(sc)} candles")
    lines.append("")
    lines.append("WARNING: HOLDOUT not used for parameter selection.")
    lines.append("")

    lines += ["## Hypothesis", f"ID: {HYP_A_001_ID}",
              f"Name: Trend Breakout",
              f"Lookback: {LOOKBACK}",
              f"Horizons: {HORIZONS}",
              f"Direction: LONG + SHORT",
              f"Code version: {CODE_VERSION}", ""]

    lines += ["## Event Counts (TRAIN)",
              f"Long events: {report.long_event_count}",
              f"Short events: {report.short_event_count}",
              f"Total: {report.total_event_count}", ""]

    lines += ["## Forward Return Results (TRAIN)", ""]
    for h in HORIZONS:
        lines.append(f"### Horizon {h}")
        for direction, key in [("LONG", "long_gross"), ("SHORT", "short_gross"), ("BASELINE A", "baseline_a")]:
            res = getattr(report, key).get(h)
            if res and res.valid_count > 0:
                lines.append(f"  {direction}: n={res.valid_count} mean={float(res.mean_return or 0):.4f} "
                              f"median={float(res.median_return or 0):.4f} "
                              f"win_rate={res.win_rate:.2f} "
                              f"std={float(res.std_return or 0):.4f}")
            else:
                lines.append(f"  {direction}: insufficient data")
        lines.append("")

    lines += ["## Cost Model",
              f"Taker fee: {TAKER_FEE_RATE} (0.055%)",
              f"Slippage estimate: {SLIPPAGE_RATE} (0.05%)",
              f"Funding: NOT INCLUDED in event study forward return",
              "Net proxy = gross return - 2 x (fee + slippage per side)", ""]

    wfr = report.walk_forward_result
    if wfr:
        lines += ["## Walk-Forward",
                  f"Total windows: {wfr.total_windows}",
                  f"Completed: {wfr.completed_windows}",
                  f"Failed: {wfr.failed_windows}",
                  f"Profitable windows: {wfr.profitable_windows}/{wfr.completed_windows}",
                  f"Window win rate: {wfr.window_win_rate:.2f}", ""]
        for w in wfr.windows:
            lines.append(f"  {w.window_id}: {w.test_start.date()} → {w.test_end.date()} "
                         f"status={w.status}")
        lines.append("")

    csr = report.cost_stress_report
    if csr:
        lines += ["## Cost Robustness"]
        for r in csr.results:
            survives = "POSITIVE" if r.metrics and r.metrics.net_pnl >= 0 else "NEGATIVE"
            lines.append(f"  {r.cost_multiplier:.2f}x slippage: {survives}")
        lines.append("")

    ev = report.edge_evaluation
    lines += ["## Edge Evaluation",
              f"Verdict: {report.final_verdict}",
              f"Reasoning: {ev.reasoning if ev else 'N/A'}", "",
              "Note: EdgeEvaluator is a research classification tool,",
              "NOT a production acceptance gate.", ""]

    lines += ["## Final Research Status",
              str(report.final_verdict), ""]

    lines += ["## Limitations",
              "- Event study only; no full trading simulation on this split",
              "- Funding not included in forward return calculation",
              "- Walk-forward used no-trade baseline strategy (infrastructure test only)",
              "- Cost stress tested on no-trade strategy (0 trades = 0 impact)",
              "- OOS and HOLDOUT splits not yet evaluated", ""]

    lines += ["## Reproducibility",
              f"Dataset hash: {dataset_hash}",
              f"Parameter hash: {report.parameter_hash}",
              f"Code version: {CODE_VERSION}", ""]

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = DOCS_DIR / "HYP-A-001_REAL_DATA_REPORT.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
