"""
HYP-C-001 TRAIN Research Run.

Loads the frozen BTCUSDT H4 dataset, runs the full HYP-C-001 event study
on the TRAIN split, and prints a structured report.

RESEARCH RULES:
- Only TRAIN split is used here.
- OOS and HOLDOUT are NOT loaded or evaluated.
- Parameters are frozen in hyp_c_001.py. No tuning.
- TRADING_DISABLED = True. No live orders.

Usage:
    cd "C:\\Users\\rusla\\проект мульти\\trading-bot новый -v3"
    python scripts/run_hyp_c_train.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import json
from datetime import datetime, timezone
from pathlib import Path

from trading_engine.research.bybit_downloader import load_raw_json
from trading_engine.research.splits import make_splits, filter_by_split
from trading_engine.research.hypotheses.hyp_c_001 import (
    make_hypothesis, make_parameter_snapshot,
    EMA_FAST_PERIOD, EMA_SLOW_PERIOD, TREND_MIN_BARS,
    PULLBACK_TOLERANCE, HORIZONS, HYP_C_001_ID, CODE_VERSION,
    TAKER_FEE_RATE, SLIPPAGE_RATE, NET_COST_RATE, WARMUP_BARS,
)
from trading_engine.research.hypotheses.study_runner_c import HypCStudyRunner
from trading_engine.research.registry import HypothesisRegistry
from trading_engine.research.results import ResultsStore
from trading_engine.research.models import SplitType

_UTC = timezone.utc
DATASETS_DIR = Path(__file__).parent.parent / "research" / "datasets"
DOCS_DIR = Path(__file__).parent.parent / "docs" / "research"
DOCS_DIR.mkdir(parents=True, exist_ok=True)

SYMBOL = "BTCUSDT"
TIMEFRAME = "H4"
DATASET_ID = f"{SYMBOL}-{TIMEFRAME}-2024-2026"
EXPECTED_DATASET_HASH_PREFIX = "e182346101e28d26"

# Canonical dataset file (not scanning directory to avoid picking up anomalous files)
CANONICAL_DATASET_FILENAME = "2024-01-01_2026-09-30.json"


def main():
    print("=" * 70)
    print("HYP-C-001 — TREND PULLBACK CONTINUATION — TRAIN RESEARCH RUN")
    print("=" * 70)
    print("RESEARCH ONLY. NO LIVE TRADING. TRADING_DISABLED=True.")
    print()

    # ── 1. Load frozen canonical dataset ─────────────────────────────────────
    print("[1] Loading frozen BTCUSDT H4 dataset...")
    raw_dir = DATASETS_DIR / "raw" / "bybit" / SYMBOL / TIMEFRAME
    canonical_path = raw_dir / CANONICAL_DATASET_FILENAME

    if not canonical_path.exists():
        # Fallback: find latest valid JSON (exclude anomalous file)
        existing = sorted(raw_dir.glob("*.json")) if raw_dir.exists() else []
        valid_files = [f for f in existing if "2026-08-28" not in f.name]
        if not valid_files:
            print(f"\n  ERROR: No dataset found at {raw_dir}")
            print("  Run scripts/run_step_7_3.py first to download the dataset.")
            sys.exit(1)
        canonical_path = sorted(valid_files)[-1]
        print(f"  WARNING: Canonical file not found, using: {canonical_path.name}")
    else:
        print(f"  Using canonical dataset: {canonical_path.name}")

    with open(canonical_path) as f:
        meta = json.load(f)

    dataset_hash = meta.get("dataset_hash", "")
    if not dataset_hash.startswith(EXPECTED_DATASET_HASH_PREFIX):
        print(f"\n  STOP CONDITION: Dataset hash mismatch!")
        print(f"  Expected prefix: {EXPECTED_DATASET_HASH_PREFIX}")
        print(f"  Actual hash:     {dataset_hash}")
        print("  Do NOT proceed. Verify the dataset file.")
        sys.exit(1)

    candles = load_raw_json(canonical_path)
    print(f"  Loaded {len(candles)} total candles")
    print(f"  Dataset hash: {dataset_hash} OK")

    # ── 2. Splits — TRAIN only ────────────────────────────────────────────────
    print("\n[2] Creating data splits (TRAIN only)...")
    splits = make_splits(DATASET_ID, dataset_hash)
    for name, split in splits.items():
        split_candles = filter_by_split(candles, split)
        marker = " << USING THIS" if name == "train" else " [NOT LOADED]"
        count_str = str(len(split_candles)) if name == "train" else "?"
        print(f"  {name.upper():12s}: {split.start.date()} - {split.end.date()} = {count_str} candles{marker}")

    train_candles = filter_by_split(candles, splits["train"])
    print(f"\n  TRAIN candles: {len(train_candles)}")
    print("  OOS and HOLDOUT NOT loaded.")

    if len(train_candles) < WARMUP_BARS + max(HORIZONS) + 10:
        print(f"\n  ERROR: Insufficient TRAIN candles: {len(train_candles)}")
        sys.exit(1)

    # ── 3. Register HYP-C-001 ─────────────────────────────────────────────────
    print("\n[3] Registering HYP-C-001...")
    registry = HypothesisRegistry()
    results_store_path = DOCS_DIR / "hyp_c_001_results.jsonl"
    results_store = ResultsStore(path=results_store_path)

    hyp = make_hypothesis(DATASET_ID)
    registered = registry.register(hyp)

    param_snap = make_parameter_snapshot(DATASET_ID, dataset_hash)
    print(f"  Hypothesis ID:        {registered.hypothesis_id}")
    print(f"  Status:               {registered.status.value}")
    print(f"  EMA fast period:      {EMA_FAST_PERIOD}")
    print(f"  EMA slow period:      {EMA_SLOW_PERIOD}")
    print(f"  Trend min bars:       {TREND_MIN_BARS}")
    print(f"  Pullback tolerance:   {PULLBACK_TOLERANCE} ({float(PULLBACK_TOLERANCE)*100:.2f}%)")
    print(f"  Horizons:             {HORIZONS}")
    print(f"  Taker fee:            {float(TAKER_FEE_RATE)*100:.4f}%")
    print(f"  Slippage:             {float(SLIPPAGE_RATE)*100:.4f}%")
    print(f"  Net cost rate:        {float(NET_COST_RATE)*100:.4f}% (one-way)")
    print(f"  Parameter hash:       {param_snap.parameter_hash}")
    print(f"  Code version:         {CODE_VERSION}")
    print(f"  Warmup bars:          {WARMUP_BARS}")

    # ── 4. Run HYP-C-001 event study on TRAIN ────────────────────────────────
    print("\n[4] Running HYP-C-001 event study on TRAIN split...")
    print("    (walk-forward=True, cost_stress=True)")
    runner = HypCStudyRunner(registry=registry, results_store=results_store)
    report = runner.run(
        candles=train_candles,
        dataset_id=DATASET_ID,
        dataset_hash=dataset_hash,
        split=splits["train"],
        run_walk_forward=True,
        run_cost_stress=True,
        wf_train_bars=300,
        wf_test_bars=100,
    )

    print(f"  Pipeline status: {report.status}")
    if report.error:
        print(f"  Error: {report.error}")
        sys.exit(1)

    print(f"\n  LONG events:  {report.long_event_count}")
    print(f"  SHORT events: {report.short_event_count}")
    print(f"  TOTAL events: {report.total_event_count}")
    print(f"  Period: {report.period_start.date()} → {report.period_end.date()}")
    print(f"  Parameter hash: {report.parameter_hash}")

    if report.total_event_count == 0:
        print("\n  WARNING: Zero HYP-C events detected on TRAIN split.")
        print("  Edge evaluation will be INCONCLUSIVE.")

    # ── 5. Forward return results ──────────────────────────────────────────────
    print("\n[5] TRAIN forward return results (gross, per horizon):")
    print(f"  {'Horizon':>8} | {'Dir':>5} | {'Count':>6} | {'Mean':>8} | {'Median':>8} | {'WinRate':>7} | {'Std':>8} | {'t-stat':>7} | {'p-value':>8}")
    print("  " + "-" * 87)

    for h in HORIZONS:
        for direction, key in [("LONG", "long_gross"), ("SHORT", "short_gross")]:
            res = getattr(report, key).get(h)
            if res is None:
                print(f"  H{h:>6} | {direction:>5} | {'N/A':>6}")
                continue
            mean = f"{float(res.mean_return):.5f}" if res.mean_return else "  N/A  "
            med  = f"{float(res.median_return):.5f}" if res.median_return else "  N/A  "
            std  = f"{float(res.std_return):.5f}" if res.std_return else "  N/A  "
            wr   = f"{res.win_rate:.4f}" if res.win_rate is not None else "  N/A  "
            ts   = f"{res.t_statistic:.3f}" if res.t_statistic is not None else "  N/A"
            pv   = f"{res.p_value:.5f}" if res.p_value is not None else "  N/A  "
            print(f"  H{h:>6} | {direction:>5} | {res.valid_count:>6} | {mean:>8} | {med:>8} | {wr:>7} | {std:>8} | {ts:>7} | {pv:>8}")

    # ── 6. Baseline comparison ────────────────────────────────────────────────
    print("\n[6] Baseline (unconditional) forward returns:")
    for h in HORIZONS:
        bl = report.baseline_a.get(h)
        bm = f"{float(bl.mean_return):.5f}" if bl and bl.mean_return else "N/A"
        bw = f"{bl.win_rate:.4f}" if bl and bl.win_rate is not None else "N/A"
        print(f"  H{h:>2}: mean={bm}  win_rate={bw}  (n={bl.valid_count if bl else 0})")

    # ── 7. Multiple testing ───────────────────────────────────────────────────
    print("\n[7] Multiple testing correction (Bonferroni + Holm):")
    mt = report.multiple_testing_tracker
    if mt is None or len(mt._records) == 0:
        print("  No tests registered (zero events or insufficient data).")
    else:
        print(f"  Tests registered: {len(mt._records)}")
        print(f"  Bonferroni threshold (α=0.05/8): {report.bonferroni_threshold:.6f}")
        print()
        print(f"  {'Test ID':>40} | {'p-value':>8} | {'Bonferroni':>10} | {'Holm':>6}")
        print("  " + "-" * 75)
        if report.holm_results:
            for rec, sig in report.holm_results:
                pv = f"{rec.p_value:.5f}" if rec.p_value is not None else "  N/A  "
                bon = "REJECT" if (rec.p_value is not None and rec.p_value < report.bonferroni_threshold) else "ACCEPT"
                holm = "SIG" if sig else "n.s."
                print(f"  {rec.test_id:>40} | {pv:>8} | {bon:>10} | {holm:>6}")

    # ── 8. Bootstrap CIs ──────────────────────────────────────────────────────
    print("\n[8] Bootstrap 95% CIs (mean return):")
    cis = report.bootstrap_cis
    for direction in ["LONG", "SHORT"]:
        dir_cis = cis.get(direction, {})
        for h in HORIZONS:
            ci = dir_cis.get(h)
            if ci is None:
                print(f"  {direction} H{h:>2}: N/A")
            else:
                contains_zero = ci.ci_lower <= 0 <= ci.ci_upper
                print(f"  {direction} H{h:>2}: [{ci.ci_lower:.5f}, {ci.ci_upper:.5f}]  (contains zero: {contains_zero})")

    # ── 9. Cost robustness ────────────────────────────────────────────────────
    print("\n[9] Cost robustness (net return after round-trip cost):")
    if report.cost_stress_summary:
        for mult in [1.0, 1.25, 1.5, 2.0]:
            row = report.cost_stress_summary.get(mult, {})
            parts = []
            for direction in ["LONG", "SHORT"]:
                per_h = row.get(direction, {})
                for h in HORIZONS:
                    val = per_h.get(h)
                    parts.append(f"{direction[:1]}H{h}={'N/A' if val is None else f'{val:.4f}'}")
            print(f"  {mult:.2f}x: {' | '.join(parts)}")
    else:
        print("  Not available (zero events).")

    # ── 10. Walk-forward ──────────────────────────────────────────────────────
    print("\n[10] Walk-forward results (event study per window):")
    wfr = report.walk_forward_result
    if wfr is None:
        print("  Walk-forward not run.")
    else:
        print(f"  Total windows:      {wfr.total_windows}")
        print(f"  Completed:          {wfr.completed_windows}")
        print(f"  Skipped (0 events): {wfr.skipped_windows}")
        print(f"  Failed:             {wfr.failed_windows}")
        if wfr.windows:
            print(f"\n  {'WF':>4} | {'Test period':>23} | {'L-events':>8} | {'S-events':>8} | {'Status':>10}")
            print("  " + "-" * 64)
            for w in wfr.windows:
                print(f"  {w.window_id:>4} | {str(w.test_start.date()):>11}→{str(w.test_end.date()):>11} | "
                      f"{w.long_event_count:>8} | {w.short_event_count:>8} | {w.status:>10}")

    # ── 11. Edge verdict ──────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("EDGE VERDICT:")
    print(f"  {report.final_verdict}")
    if report.edge_evaluation:
        reason = report.edge_evaluation.reasoning
        print(f"\nReasoning (truncated):\n  {reason[:500]}")
    print("=" * 70)

    # ── 12. Results store ─────────────────────────────────────────────────────
    print(f"\n[12] Results stored: {results_store.count()} run(s)")
    print(f"     Path: {results_store_path}")

    print("\n" + "=" * 70)
    print("HYP-C-001 TRAIN RESEARCH COMPLETE.")
    print()
    print("NEXT STEPS:")
    print("  1. Review this report.")
    print("  2. Document verdict in HYP-C-001_REPORT.md.")
    print("  3. DO NOT advance to OOS without documenting TRAIN findings.")
    print("  4. DO NOT use HOLDOUT.")
    print("  5. WEAK/REJECTED is an acceptable research outcome.")
    print("=" * 70)

    return report


if __name__ == "__main__":
    main()
