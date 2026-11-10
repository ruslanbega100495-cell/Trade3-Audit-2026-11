"""
HYP-E-001 HOLDOUT Research Run — Phase 8.

Applies the frozen HYP-E-001 (MOMENTUM_LOOKBACK=4, MOMENTUM_THRESHOLD=0.01,
VOLUME_LOOKBACK=20, VOLUME_RATIO_THRESHOLD=1.5) to the HOLDOUT period
[2025-10-01, 2026-10-01) without modifying any parameters.

This is a ONE-SHOT, FINAL evaluation. Once run, results are locked.

RESEARCH RULES:
- HOLDOUT period only: 2025-10-01 inclusive to 2026-10-01 exclusive.
- OOS and HOLDOUT (as labeled in splits.py) are both included here —
  neither was previously touched; combined = unseen data.
- TRAIN and VALIDATION NOT used for any calculation in this script.
- Parameters are frozen in hyp_e_001.py. No tuning. No grid search.
- TRADING_DISABLED = True. No live orders.
- parameter_hash MUST equal 6da3073a65dd08f8.
- dataset_hash MUST start with e182346101e28d26.
- ONE run only. No second experiments.

Usage:
    cd "C:\\Users\\rusla\\проект мульти\\trading-bot новый -v3"
    python -X utf8 scripts/run_hyp_e_holdout.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import json
from datetime import datetime, timezone
from pathlib import Path
from decimal import Decimal

from trading_engine.research.bybit_downloader import load_raw_json
from trading_engine.research.splits import make_splits, filter_by_split
from trading_engine.research.models import DataSplit, SplitType
from trading_engine.research.holdout import HoldoutLock
from trading_engine.research.hypotheses.hyp_e_001 import (
    make_hypothesis, make_parameter_snapshot,
    MOMENTUM_LOOKBACK, MOMENTUM_THRESHOLD,
    VOLUME_LOOKBACK, VOLUME_RATIO_THRESHOLD,
    HORIZONS, HYP_E_001_ID, CODE_VERSION,
    TAKER_FEE_RATE, SLIPPAGE_RATE, NET_COST_RATE, WARMUP_BARS,
)
from trading_engine.research.hypotheses.study_runner_e import HypEStudyRunner
from trading_engine.research.registry import HypothesisRegistry
from trading_engine.research.results import ResultsStore

_UTC = timezone.utc

DATASETS_DIR = Path(__file__).parent.parent / "research" / "datasets"
DOCS_DIR = Path(__file__).parent.parent / "docs" / "research"
DOCS_DIR.mkdir(parents=True, exist_ok=True)

SYMBOL = "BTCUSDT"
TIMEFRAME = "H4"
DATASET_ID = f"{SYMBOL}-{TIMEFRAME}-2024-2026"
EXPECTED_DATASET_HASH_PREFIX = "e182346101e28d26"
EXPECTED_PARAMETER_HASH = "6da3073a65dd08f8"
CANONICAL_DATASET_FILENAME = "2024-01-01_2026-09-30.json"

# HOLDOUT boundaries per user-specified Phase 8 protocol
HOLDOUT_START = datetime(2025, 10, 1, tzinfo=_UTC)
HOLDOUT_END   = datetime(2026, 10, 1, tzinfo=_UTC)  # exclusive


def main():
    print("=" * 70)
    print("HYP-E-001 -- MOMENTUM + VOLUME -- HOLDOUT (PHASE 8)")
    print("=" * 70)
    print("RESEARCH ONLY. NO LIVE TRADING. TRADING_DISABLED=True.")
    print("HOLDOUT period: 2025-10-01 to 2026-10-01 (unseen, never touched).")
    print("ONE SHOT. This is the final evaluation. No repeats allowed.")
    print()

    # ── PRE-HOLDOUT AUDIT ─────────────────────────────────────────────────────
    print("=" * 70)
    print("PRE-HOLDOUT AUDIT")
    print("=" * 70)
    print(f"  Expected parameter_hash : {EXPECTED_PARAMETER_HASH}")
    print(f"  Expected dataset_hash   : {EXPECTED_DATASET_HASH_PREFIX}")
    print(f"  HYP-E-001 ID            : {HYP_E_001_ID}")
    print(f"  CODE_VERSION            : {CODE_VERSION}")
    print(f"  HOLDOUT start (incl)    : {HOLDOUT_START.date()}")
    print(f"  HOLDOUT end   (excl)    : {HOLDOUT_END.date()}")
    print()

    # A. Verify frozen parameters
    print("[A] Frozen parameter audit:")
    print(f"  MOMENTUM_LOOKBACK      = {MOMENTUM_LOOKBACK}  (expected: 4)")
    print(f"  MOMENTUM_THRESHOLD     = {MOMENTUM_THRESHOLD}  (expected: 0.01)")
    print(f"  VOLUME_LOOKBACK        = {VOLUME_LOOKBACK}  (expected: 20)")
    print(f"  VOLUME_RATIO_THRESHOLD = {VOLUME_RATIO_THRESHOLD}  (expected: 1.5)")
    print(f"  HORIZONS               = {HORIZONS}  (expected: [4, 8, 16, 32])")
    print(f"  NET_COST_RATE          = {float(NET_COST_RATE)*100:.4f}%  (expected: 0.1050%)")
    param_errors = []
    if MOMENTUM_LOOKBACK != 4: param_errors.append("MOMENTUM_LOOKBACK != 4")
    if MOMENTUM_THRESHOLD != 0.01: param_errors.append("MOMENTUM_THRESHOLD != 0.01")
    if VOLUME_LOOKBACK != 20: param_errors.append("VOLUME_LOOKBACK != 20")
    if VOLUME_RATIO_THRESHOLD != 1.5: param_errors.append("VOLUME_RATIO_THRESHOLD != 1.5")
    if HORIZONS != [4, 8, 16, 32]: param_errors.append("HORIZONS != [4,8,16,32]")
    if param_errors:
        print(f"\n  AUDIT FAILED — parameter mismatch: {param_errors}")
        sys.exit(1)
    print("  Parameters: PASS")

    # B. Load dataset
    print("\n[B] Loading frozen BTCUSDT H4 dataset...")
    raw_dir = DATASETS_DIR / "raw" / "bybit" / SYMBOL / TIMEFRAME
    canonical_path = raw_dir / CANONICAL_DATASET_FILENAME
    if not canonical_path.exists():
        existing = sorted(raw_dir.glob("*.json")) if raw_dir.exists() else []
        valid_files = [f for f in existing if "2026-08-28" not in f.name]
        if not valid_files:
            print(f"\n  ERROR: No dataset found at {raw_dir}")
            sys.exit(1)
        canonical_path = sorted(valid_files)[-1]
        print(f"  WARNING: Canonical file not found, using: {canonical_path.name}")
    else:
        print(f"  Using canonical dataset: {canonical_path.name}")

    with open(canonical_path) as f:
        meta = json.load(f)
    dataset_hash = meta.get("dataset_hash", "")
    if not dataset_hash.startswith(EXPECTED_DATASET_HASH_PREFIX):
        print(f"\n  AUDIT FAILED — dataset hash mismatch!")
        print(f"  Expected prefix: {EXPECTED_DATASET_HASH_PREFIX}")
        print(f"  Actual hash:     {dataset_hash}")
        sys.exit(1)

    candles = load_raw_json(canonical_path)
    print(f"  Loaded {len(candles)} total candles")
    print(f"  Dataset hash: {dataset_hash}  PASS")

    # C. Verify parameter hash
    print("\n[C] Verifying parameter hash...")
    param_snap = make_parameter_snapshot(DATASET_ID, dataset_hash)
    if param_snap.parameter_hash != EXPECTED_PARAMETER_HASH:
        print(f"\n  AUDIT FAILED — parameter hash changed!")
        print(f"  Expected: {EXPECTED_PARAMETER_HASH}")
        print(f"  Actual:   {param_snap.parameter_hash}")
        sys.exit(1)
    print(f"  Parameter hash: {param_snap.parameter_hash}  PASS")

    # D. Holdout lock
    print("\n[D] Holdout lock check...")
    splits = make_splits(DATASET_ID, dataset_hash)
    holdout_split_code = splits["holdout"]  # used for lock only
    lock = HoldoutLock.lock(holdout_split_code)
    # Request FINAL_EVALUATION — this will consume the lock (one-shot protection)
    lock.request_use("FINAL_EVALUATION")
    print(f"  HoldoutLock: LOCKED, purpose=FINAL_EVALUATION, consumed={lock.is_consumed}")
    print("  TRAIN: NOT loaded for any holdout metric.")
    print("  VALIDATION: NOT loaded for any holdout metric.")

    # E. Extract HOLDOUT candles (2025-10-01 to 2026-10-01)
    print("\n[E] Extracting HOLDOUT candles...")
    holdout_candles = [
        c for c in candles
        if HOLDOUT_START <= c.open_time < HOLDOUT_END
    ]
    if not holdout_candles:
        print("  ERROR: No HOLDOUT candles found!")
        sys.exit(1)

    holdout_candles.sort(key=lambda c: c.open_time)
    hc_first = holdout_candles[0].open_time.date()
    hc_last  = holdout_candles[-1].open_time.date()
    print(f"  HOLDOUT candles: {len(holdout_candles)}")
    print(f"  First bar: {hc_first}")
    print(f"  Last bar:  {hc_last}")

    # overlap check: ensure no TRAIN or VALIDATION candles leaked
    from trading_engine.research.splits import SPLIT_BOUNDARIES
    train_end = SPLIT_BOUNDARIES["train_end"]
    val_end   = SPLIT_BOUNDARIES["validation_end"]
    overlap = [c for c in holdout_candles if c.open_time < val_end]
    if overlap:
        print(f"\n  AUDIT FAILED — {len(overlap)} HOLDOUT candles overlap with TRAIN/VALIDATION!")
        sys.exit(1)
    print("  Overlap check: PASS (no TRAIN/VALIDATION contamination)")

    if len(holdout_candles) < WARMUP_BARS + max(HORIZONS) + 10:
        print(f"\n  ERROR: Insufficient HOLDOUT candles: {len(holdout_candles)}")
        sys.exit(1)

    # F. Build a DataSplit object for HOLDOUT period
    holdout_split = DataSplit(
        split_type=SplitType.HOLDOUT,
        start=HOLDOUT_START,
        end=HOLDOUT_END,
        dataset_id=DATASET_ID,
        dataset_hash=dataset_hash,
    )

    print()
    print("=" * 70)
    print("PRE-HOLDOUT AUDIT: PASS")
    print("=" * 70)
    print()

    # ── HOLDOUT RUN ───────────────────────────────────────────────────────────
    print("[1] Registering HYP-E-001 (HOLDOUT run)...")
    registry = HypothesisRegistry()
    results_store_path = DOCS_DIR / "hyp_e_001_holdout_results.jsonl"
    results_store = ResultsStore(path=results_store_path)

    hyp = make_hypothesis(DATASET_ID)
    registered = registry.register(hyp)
    print(f"  Hypothesis ID:  {registered.hypothesis_id}")
    print(f"  Status:         {registered.status.value}")
    print(f"  Results store:  {results_store_path.name}")
    print(f"  TRAIN results PRESERVED at:      hyp_e_001_results.jsonl")
    print(f"  VALIDATION results PRESERVED at: hyp_e_001_validation_results.jsonl")

    print("\n[2] Running HYP-E-001 event study on HOLDOUT (one-shot, frozen params)...")
    print("    walk-forward=True, cost_stress=True")
    print("    IDENTICAL runner to TRAIN/VALIDATION — no modifications.")
    runner = HypEStudyRunner(registry=registry, results_store=results_store)
    report = runner.run(
        candles=holdout_candles,
        dataset_id=DATASET_ID,
        dataset_hash=dataset_hash,
        split=holdout_split,
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
    print(f"  Period: {report.period_start.date()} - {report.period_end.date()}")
    print(f"  Parameter hash: {report.parameter_hash}")

    if report.parameter_hash != EXPECTED_PARAMETER_HASH:
        print(f"\n  AUDIT FAILED — parameter hash changed during run!")
        sys.exit(1)
    print("  Post-run parameter hash: PASS")

    if report.total_event_count == 0:
        print("\n  WARNING: Zero events detected on HOLDOUT split. INCONCLUSIVE.")

    # [3] Forward return results
    print("\n[3] HOLDOUT forward return results (gross):")
    print(f"  {'Horizon':>8} | {'Dir':>5} | {'Count':>6} | {'Mean':>9} | {'Median':>9} | {'WinRate':>7} | {'Std':>9} | {'t-stat':>7} | {'p-value':>8}")
    print("  " + "-" * 91)
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
            print(f"  H{h:>6} | {direction:>5} | {res.valid_count:>6} | {mean:>9} | {med:>9} | {wr:>7} | {std:>9} | {ts:>7} | {pv:>8}")

    # [4] Baseline
    print("\n[4] Baseline (unconditional) forward returns on HOLDOUT:")
    for h in HORIZONS:
        bl = report.baseline_a.get(h)
        bm = f"{float(bl.mean_return):.5f}" if bl and bl.mean_return else "N/A"
        bw = f"{bl.win_rate:.4f}" if bl and bl.win_rate is not None else "N/A"
        print(f"  H{h:>2}: mean={bm}  win_rate={bw}  (n={bl.valid_count if bl else 0})")

    # [5] Multiple testing
    print("\n[5] Multiple testing (Bonferroni + Holm):")
    mt = report.multiple_testing_tracker
    if mt is None or len(mt._records) == 0:
        print("  No tests registered (zero events or insufficient data).")
    else:
        n_tests = len(mt._records)
        print(f"  Tests registered: {n_tests}")
        print(f"  Bonferroni threshold (0.05/{n_tests}): {report.bonferroni_threshold:.6f}")
        print()
        print(f"  {'Test ID':>40} | {'p-value':>8} | {'Bonferroni':>10} | {'Holm':>6}")
        print("  " + "-" * 75)
        if report.holm_results:
            for rec, sig in report.holm_results:
                pv = f"{rec.p_value:.5f}" if rec.p_value is not None else "  N/A  "
                bon = "REJECT" if (rec.p_value is not None and rec.p_value < report.bonferroni_threshold) else "ACCEPT"
                holm = "SIG" if sig else "n.s."
                print(f"  {rec.test_id:>40} | {pv:>8} | {bon:>10} | {holm:>6}")

    # [6] Bootstrap CIs
    print("\n[6] Bootstrap 95% CIs (mean return):")
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

    # [7] Cost robustness
    print("\n[7] Cost robustness (net after round-trip cost):")
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
        print("  Not available.")

    # [8] Walk-forward
    print("\n[8] Walk-forward results:")
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
                print(f"  {w.window_id:>4} | {str(w.test_start.date()):>11}-{str(w.test_end.date()):>11} | "
                      f"{w.long_event_count:>8} | {w.short_event_count:>8} | {w.status:>10}")

    # [9] Edge verdict
    print("\n" + "=" * 70)
    print("EDGE VERDICT (HOLDOUT):")
    print(f"  {report.final_verdict}")
    if report.edge_evaluation:
        reason = report.edge_evaluation.reasoning
        print(f"\nReasoning (truncated):\n  {reason[:600]}")
    print("=" * 70)

    # [10] Results stored
    print(f"\n[10] Results stored: {results_store.count()} run(s)")
    print(f"     Path: {results_store_path}")
    print(f"     TRAIN results preserved:      hyp_e_001_results.jsonl")
    print(f"     VALIDATION results preserved: hyp_e_001_validation_results.jsonl")

    print("\n" + "=" * 70)
    print("HYP-E-001 HOLDOUT RESEARCH COMPLETE.")
    print()
    print("IMPORTANT:")
    print("  1. This was the ONE-SHOT, FINAL HOLDOUT evaluation.")
    print("  2. Do NOT modify parameters based on this result.")
    print("  3. Do NOT run a second HOLDOUT experiment.")
    print("  4. Do NOT start HYP-F based on this result automatically.")
    print("  5. TRADING_DISABLED=True remains. Not production-ready.")
    print("=" * 70)

    return report


if __name__ == "__main__":
    main()
