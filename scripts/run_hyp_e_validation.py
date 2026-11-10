"""
HYP-E-001 VALIDATION Research Run.

Applies the frozen HYP-E-001 (MOMENTUM_LOOKBACK=4, MOMENTUM_THRESHOLD=0.01,
VOLUME_LOOKBACK=20, VOLUME_RATIO_THRESHOLD=1.5) to the VALIDATION split
[2025-04-01, 2025-10-01) without modifying any parameters.

RESEARCH RULES:
- VALIDATION split only. TRAIN used only for comparison reference.
- OOS is NOT loaded or evaluated.
- HOLDOUT is NOT loaded or evaluated.
- Parameters are frozen in hyp_e_001.py. No tuning.
- TRADING_DISABLED = True. No live orders.
- parameter_hash MUST equal 6da3073a65dd08f8.
- dataset_hash MUST start with e182346101e28d26.

Usage:
    cd "C:\\Users\\rusla\\проект мульти\\trading-bot новый -v3"
    python -X utf8 scripts/run_hyp_e_validation.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import json
from pathlib import Path

from trading_engine.research.bybit_downloader import load_raw_json
from trading_engine.research.splits import make_splits, filter_by_split
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

DATASETS_DIR = Path(__file__).parent.parent / "research" / "datasets"
DOCS_DIR = Path(__file__).parent.parent / "docs" / "research"
DOCS_DIR.mkdir(parents=True, exist_ok=True)

SYMBOL = "BTCUSDT"
TIMEFRAME = "H4"
DATASET_ID = f"{SYMBOL}-{TIMEFRAME}-2024-2026"
EXPECTED_DATASET_HASH_PREFIX = "e182346101e28d26"
EXPECTED_PARAMETER_HASH = "6da3073a65dd08f8"
CANONICAL_DATASET_FILENAME = "2024-01-01_2026-09-30.json"


def main():
    print("=" * 70)
    print("HYP-E-001 -- MOMENTUM + VOLUME -- VALIDATION RESEARCH RUN")
    print("=" * 70)
    print("RESEARCH ONLY. NO LIVE TRADING. TRADING_DISABLED=True.")
    print("VALIDATION split only. OOS and HOLDOUT NOT loaded.")
    print()

    # PRE-VALIDATION AUDIT
    print("PRE-VALIDATION AUDIT")
    print(f"  Expected parameter_hash : {EXPECTED_PARAMETER_HASH}")
    print(f"  Expected dataset_hash   : {EXPECTED_DATASET_HASH_PREFIX}")
    print(f"  HYP-E-001 ID            : {HYP_E_001_ID}")
    print(f"  CODE_VERSION            : {CODE_VERSION}")
    print()

    # 1. Load frozen canonical dataset
    print("[1] Loading frozen BTCUSDT H4 dataset...")
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
        print(f"\n  VALIDATION BLOCKED — dataset hash mismatch!")
        print(f"  Expected prefix: {EXPECTED_DATASET_HASH_PREFIX}")
        print(f"  Actual hash:     {dataset_hash}")
        sys.exit(1)

    candles = load_raw_json(canonical_path)
    print(f"  Loaded {len(candles)} total candles")
    print(f"  Dataset hash: {dataset_hash} OK")

    # 2. Verify parameter hash before any run
    print("\n[2] Verifying parameter hash...")
    param_snap = make_parameter_snapshot(DATASET_ID, dataset_hash)
    if param_snap.parameter_hash != EXPECTED_PARAMETER_HASH:
        print(f"\n  VALIDATION BLOCKED — parameter hash changed!")
        print(f"  Expected: {EXPECTED_PARAMETER_HASH}")
        print(f"  Actual:   {param_snap.parameter_hash}")
        sys.exit(1)
    print(f"  Parameter hash: {param_snap.parameter_hash} OK")
    print(f"  Momentum lookback:      {MOMENTUM_LOOKBACK}")
    print(f"  Momentum threshold:     {MOMENTUM_THRESHOLD:.4f}")
    print(f"  Volume lookback:        {VOLUME_LOOKBACK}")
    print(f"  Volume ratio threshold: {VOLUME_RATIO_THRESHOLD}")
    print(f"  Horizons:               {HORIZONS}")
    print(f"  Net cost rate:          {float(NET_COST_RATE)*100:.4f}% (one-way)")
    print(f"  Warmup bars:            {WARMUP_BARS}")

    # 3. Splits — VALIDATION only
    print("\n[3] Creating data splits (VALIDATION only)...")
    splits = make_splits(DATASET_ID, dataset_hash)
    for name, split in splits.items():
        split_candles = filter_by_split(candles, split)
        if name == "validation":
            marker = " << USING THIS"
            count_str = str(len(split_candles))
        elif name == "train":
            marker = " [reference only, NOT re-used for optimization]"
            count_str = str(len(split_candles))
        else:
            marker = " [NOT LOADED]"
            count_str = "?"
        print(f"  {name.upper():12s}: {split.start.date()} - {split.end.date()} = {count_str} candles{marker}")

    validation_candles = filter_by_split(candles, splits["validation"])
    print(f"\n  VALIDATION candles: {len(validation_candles)}")
    print("  OOS and HOLDOUT NOT loaded.")

    if len(validation_candles) < WARMUP_BARS + max(HORIZONS) + 10:
        print(f"\n  ERROR: Insufficient VALIDATION candles: {len(validation_candles)}")
        sys.exit(1)

    # 4. Holdout lock check
    print("\n[4] Holdout lock check...")
    print("  HOLDOUT split: NOT loaded, NOT evaluated, NOT accessed.")
    print("  OOS split:     NOT loaded, NOT evaluated.")
    print("  Holdout lock: PASS")

    # 5. Register HYP-E-001 (existing hypothesis, not new)
    print("\n[5] Registering HYP-E-001 (VALIDATION run)...")
    registry = HypothesisRegistry()
    results_store_path = DOCS_DIR / "hyp_e_001_validation_results.jsonl"
    results_store = ResultsStore(path=results_store_path)

    hyp = make_hypothesis(DATASET_ID)
    registered = registry.register(hyp)
    print(f"  Hypothesis ID:  {registered.hypothesis_id}")
    print(f"  Status:         {registered.status.value}")
    print(f"  Results store:  {results_store_path.name} (separate from TRAIN results)")

    # 6. Run HYP-E-001 event study on VALIDATION
    print("\n[6] Running HYP-E-001 event study on VALIDATION split...")
    print("    (walk-forward=True, cost_stress=True)")
    print("    Using IDENTICAL runner as TRAIN — no modifications.")
    runner = HypEStudyRunner(registry=registry, results_store=results_store)
    report = runner.run(
        candles=validation_candles,
        dataset_id=DATASET_ID,
        dataset_hash=dataset_hash,
        split=splits["validation"],
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

    # Verify parameter hash didn't change during run
    if report.parameter_hash != EXPECTED_PARAMETER_HASH:
        print(f"\n  VALIDATION BLOCKED — parameter hash changed during run!")
        print(f"  Expected: {EXPECTED_PARAMETER_HASH}")
        print(f"  Actual:   {report.parameter_hash}")
        sys.exit(1)

    if report.total_event_count == 0:
        print("\n  WARNING: Zero HYP-E events detected on VALIDATION split.")
        print("  INCONCLUSIVE — insufficient data.")

    # 7. Forward return results
    print("\n[7] VALIDATION forward return results (gross, per horizon):")
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

    # 8. Baseline comparison
    print("\n[8] Baseline (unconditional) forward returns on VALIDATION:")
    for h in HORIZONS:
        bl = report.baseline_a.get(h)
        bm = f"{float(bl.mean_return):.5f}" if bl and bl.mean_return else "N/A"
        bw = f"{bl.win_rate:.4f}" if bl and bl.win_rate is not None else "N/A"
        print(f"  H{h:>2}: mean={bm}  win_rate={bw}  (n={bl.valid_count if bl else 0})")

    # 9. Multiple testing
    print("\n[9] Multiple testing correction (Bonferroni + Holm):")
    mt = report.multiple_testing_tracker
    if mt is None or len(mt._records) == 0:
        print("  No tests registered (zero events or insufficient data).")
    else:
        print(f"  Tests registered: {len(mt._records)}")
        print(f"  Bonferroni threshold (a=0.05/{len(mt._records)}): {report.bonferroni_threshold:.6f}")
        print()
        print(f"  {'Test ID':>40} | {'p-value':>8} | {'Bonferroni':>10} | {'Holm':>6}")
        print("  " + "-" * 75)
        if report.holm_results:
            for rec, sig in report.holm_results:
                pv = f"{rec.p_value:.5f}" if rec.p_value is not None else "  N/A  "
                bon = "REJECT" if (rec.p_value is not None and rec.p_value < report.bonferroni_threshold) else "ACCEPT"
                holm = "SIG" if sig else "n.s."
                print(f"  {rec.test_id:>40} | {pv:>8} | {bon:>10} | {holm:>6}")

    # 10. Bootstrap CIs
    print("\n[10] Bootstrap 95% CIs (mean return) on VALIDATION:")
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

    # 11. Cost robustness
    print("\n[11] Cost robustness (net return after round-trip cost):")
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

    # 12. Walk-forward
    print("\n[12] Walk-forward results (event study per window):")
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

    # 13. Edge verdict
    print("\n" + "=" * 70)
    print("EDGE VERDICT (VALIDATION):")
    print(f"  {report.final_verdict}")
    if report.edge_evaluation:
        reason = report.edge_evaluation.reasoning
        print(f"\nReasoning (truncated):\n  {reason[:600]}")
    print("=" * 70)

    # 14. Results store
    print(f"\n[14] Results stored: {results_store.count()} run(s)")
    print(f"     Path: {results_store_path}")
    print(f"     TRAIN results preserved at: hyp_e_001_results.jsonl")

    print("\n" + "=" * 70)
    print("HYP-E-001 VALIDATION RESEARCH COMPLETE.")
    print()
    print("NEXT STEPS:")
    print("  1. Review this report.")
    print("  2. Document verdict in HYP-E-001_VALIDATION_REPORT.md.")
    print("  3. DO NOT advance to OOS/HOLDOUT automatically.")
    print("  4. DO NOT modify parameters based on VALIDATION result.")
    print("  5. DO NOT optimize. This is an honest out-of-sample check.")
    print("=" * 70)

    return report


if __name__ == "__main__":
    main()
