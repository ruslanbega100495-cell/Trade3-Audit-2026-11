"""
Regime-Conditional Event Study — TRAIN split.

Runs HYP-A through HYP-F on the TRAIN split (2024-01-01 → 2025-04-01)
conditioned on MarketRegime. Produces a Strategy × Regime verdict matrix.

CONSTRAINTS (immutable):
  - TRADING_DISABLED = True
  - Only TRAIN split. OOS and HOLDOUT NOT loaded.
  - Pre-registered parameters of each hypothesis NOT changed.
  - No parameter tuning after seeing results.
  - HOLDOUT consumed for HYP-E. Not touched here.

Usage:
    cd "C:\\Users\\rusla\\проект мульти\\trading-bot новый -v3"
    python scripts/run_regime_train.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from trading_engine.data.models import CandleRecord
from trading_engine.research.bybit_downloader import load_raw_json
from trading_engine.research.event_study import EventStudyEngine, EventStudyResult
from trading_engine.research.regime.detector import MarketRegime, MarketRegimeDetector, WARMUP_BARS
from trading_engine.research.regime.labeler import RegimeLabeler, RegimeLabelRecord
from trading_engine.research.splits import make_splits, filter_by_split
from trading_engine.research.statistics import StatisticsEngine, MultipleTestingTracker, MultipleTestingRecord

# ── Strategy imports ───────────────────────────────────────────────────────────
from trading_engine.research.hypotheses.hyp_a_001 import (
    detect_breakout_events as detect_a,
    HORIZONS as HORIZONS_A, HYP_A_001_ID, NET_COST_RATE as COST_A,
    make_parameter_snapshot as snap_a,
)
from trading_engine.research.hypotheses.hyp_b_001 import (
    HYP_B_001_ID, HORIZONS as HORIZONS_B, NET_COST_RATE as COST_B,
    make_parameter_snapshot as snap_b,
    detect_breakout_retest_events as detect_b,
)
from trading_engine.research.hypotheses.hyp_c_001 import (
    detect_trend_pullback_events as detect_c,
    HORIZONS as HORIZONS_C, HYP_C_001_ID, NET_COST_RATE as COST_C,
    make_parameter_snapshot as snap_c,
)
from trading_engine.research.hypotheses.hyp_d_001 import (
    detect_volatility_expansion_events as detect_d,
    HORIZONS as HORIZONS_D, HYP_D_001_ID, NET_COST_RATE as COST_D,
    make_parameter_snapshot as snap_d,
)
from trading_engine.research.hypotheses.hyp_e_001 import (
    detect_momentum_volume_events as detect_e,
    HORIZONS as HORIZONS_E, HYP_E_001_ID, NET_COST_RATE as COST_E,
    make_parameter_snapshot as snap_e,
)
from trading_engine.research.hypotheses.hyp_f_001 import (
    detect_oi_expansion_events as detect_f,
    align_oi_to_candles, load_oi_series,
    HORIZONS as HORIZONS_F, HYP_F_001_ID, NET_COST_RATE as COST_F,
    make_parameter_snapshot as snap_f,
)

_UTC = timezone.utc

DATASETS_DIR = Path(__file__).parent.parent / "research" / "datasets"
DOCS_DIR = Path(__file__).parent.parent / "docs" / "research"
DOCS_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR = Path(__file__).parent.parent / "docs" / "regime_research"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

SYMBOL = "BTCUSDT"
TIMEFRAME = "H4"
DATASET_ID = f"{SYMBOL}-{TIMEFRAME}-2024-2026"
EXPECTED_HASH_PREFIX = "e182346101e28d26"

MIN_EVENTS = 30            # minimum events to compute statistics
MIN_EVENTS_STRICT = 50     # minimum events for SUPPORTED verdict
WF_N_WINDOWS = 4           # walk-forward window count within TRAIN
ALPHA = 0.05
N_BOOTSTRAP = 1000
STATS = StatisticsEngine(seed=42)

ALL_REGIMES = [r for r in MarketRegime if r != MarketRegime.UNKNOWN]
STRATEGY_IDS = [HYP_A_001_ID, HYP_B_001_ID, HYP_C_001_ID,
                HYP_D_001_ID, HYP_E_001_ID, HYP_F_001_ID]


# ── Event available_at extractors (per-strategy field name differences) ────────

def _event_avail_at(ev, hyp_id: str) -> datetime:
    if hyp_id in (HYP_B_001_ID,):
        return ev.confirmation_available_at
    if hyp_id in (HYP_C_001_ID,):
        return ev.confirmation_available_at
    if hyp_id == HYP_D_001_ID:
        return ev.expansion_available_at
    return ev.available_at  # HYP-A, HYP-E, HYP-F


# ── Regime event filter ────────────────────────────────────────────────────────

def filter_events_by_regime(
    events: list,
    avail_to_regime: dict[datetime, MarketRegime],
    hyp_id: str,
    target: MarketRegime,
) -> list:
    return [
        ev for ev in events
        if avail_to_regime.get(_event_avail_at(ev, hyp_id)) == target
    ]


# ── Raw return collector ───────────────────────────────────────────────────────

def _collect_raw(
    candles: list[CandleRecord],
    event_times: list[datetime],
    horizon: int,
    net_cost: Decimal,
    direction: str,   # "LONG" | "SHORT"
) -> list[float]:
    avail_idx = {c.available_at: i for i, c in enumerate(candles)}
    sign = 1.0 if direction == "LONG" else -1.0
    raw = []
    for et in event_times:
        idx = avail_idx.get(et)
        if idx is None:
            continue
        fwd = idx + horizon
        if fwd < len(candles):
            trig = candles[idx].close
            if trig == Decimal("0"):
                continue
            gross = float((candles[fwd].close - trig) / trig)
            net = sign * gross - float(net_cost) * 2
            raw.append(net)
    return raw


# ── Temporal walk-forward (event-study based, no trading) ─────────────────────

def _wf_sign_consistency(
    candles: list[CandleRecord],
    long_times: list[datetime],
    short_times: list[datetime],
    horizons: list[int],
    n_windows: int = WF_N_WINDOWS,
) -> dict:
    """
    Split TRAIN into n_windows sequential chunks.
    For each chunk, compute mean return at each horizon for LONG and SHORT.
    Returns {direction: {horizon: [window_means]}}.
    """
    n = len(candles)
    window_size = n // n_windows
    results: dict[str, dict[int, list[float]]] = {
        "LONG": {h: [] for h in horizons},
        "SHORT": {h: [] for h in horizons},
    }
    avail_set_long = set(long_times)
    avail_set_short = set(short_times)

    for w in range(n_windows):
        start = w * window_size
        end = start + window_size if w < n_windows - 1 else n
        wcandles = candles[start:end]
        wset_long = {t for t in avail_set_long if any(c.available_at == t for c in wcandles)}
        wset_short = {t for t in avail_set_short if any(c.available_at == t for c in wcandles)}

        for direction, wset in [("LONG", wset_long), ("SHORT", wset_short)]:
            if not wset:
                for h in horizons:
                    results[direction][h].append(None)
                continue
            engine = EventStudyEngine(
                event_times=list(wset),
                candles=wcandles,
                horizons=horizons,
                hypothesis_id="WF-WINDOW",
            )
            wf_res = engine.run()
            for h in horizons:
                r = wf_res.get(h)
                if r and r.mean_return is not None:
                    results[direction][h].append(float(r.mean_return))
                else:
                    results[direction][h].append(None)

    return results


# ── Verdict engine ─────────────────────────────────────────────────────────────

def _verdict(
    n_events: int,
    study_results: dict[int, EventStudyResult],
    bootstrap_cis: dict,
    holm_significant: set[str],
    wf_sign_rates: dict[str, float],  # direction → fraction of WF windows with expected sign
    direction: str,
    net_cost: Decimal,
    horizons: list[int],
    hyp_id: str,
) -> tuple[str, str]:
    """
    Returns (verdict_str, reason_str).
    Verdicts: SUPPORTED | WEAK | FRAGILE | INCONCLUSIVE | REJECTED | INSUFFICIENT_DATA
    """
    if n_events < MIN_EVENTS:
        return "INSUFFICIENT_DATA", f"n={n_events} < {MIN_EVENTS}"

    sign = 1.0 if direction == "LONG" else -1.0
    best_h = None
    best_p = 1.0
    best_net_mean = None

    for h in horizons:
        r = study_results.get(h)
        if r is None or r.valid_count < 2 or r.mean_return is None:
            continue
        net_mean = sign * float(r.mean_return) - float(net_cost) * 2
        test_key = f"{hyp_id}-{direction}-H{h}"
        p = r.p_value if r.p_value is not None else 1.0
        if p < best_p:
            best_p = p
            best_h = h
            best_net_mean = net_mean

    if best_h is None:
        return "INCONCLUSIVE", "No valid results at any horizon"

    # Multiple testing: Holm-significant test at best_h?
    test_key = f"{hyp_id}-{direction}-H{best_h}"
    holm_sig = test_key in holm_significant

    # Bootstrap CI at best horizon
    ci = bootstrap_cis.get(direction, {}).get(best_h)
    ci_positive = (ci is not None and ci.ci_lower > 0) if direction == "LONG" else (ci is not None and ci.ci_upper < 0)

    # Walk-forward sign consistency
    wf_rate = wf_sign_rates.get(direction, 0.0)

    # Verdict logic
    reason_parts = [
        f"n={n_events}",
        f"best_H={best_h}",
        f"net_mean={best_net_mean:.5f}" if best_net_mean is not None else "",
        f"p={best_p:.4f}",
        f"holm={'SIG' if holm_sig else 'ns'}",
        f"ci={'excl0' if ci_positive else 'incl0'}",
        f"wf_rate={wf_rate:.2f}",
    ]
    reason = " | ".join(p for p in reason_parts if p)

    if (
        n_events >= MIN_EVENTS_STRICT
        and holm_sig
        and ci_positive
        and best_net_mean is not None and best_net_mean > 0
        and wf_rate >= 0.75
    ):
        return "SUPPORTED", reason

    if (
        n_events >= MIN_EVENTS
        and best_p < ALPHA
        and best_net_mean is not None and best_net_mean > 0
        and wf_rate >= 0.5
    ):
        return "WEAK", reason

    if wf_rate < 0.5 and n_events >= MIN_EVENTS and best_p < ALPHA:
        return "FRAGILE", reason

    if best_net_mean is not None and best_net_mean < 0:
        return "REJECTED", reason

    return "INCONCLUSIVE", reason


# ── Strategy event runner ──────────────────────────────────────────────────────

def run_one_strategy(
    hyp_id: str,
    long_events: list,
    short_events: list,
    train_candles: list[CandleRecord],
    avail_to_regime: dict[datetime, MarketRegime],
    horizons: list[int],
    net_cost: Decimal,
    dataset_id: str,
    dataset_hash: str,
) -> dict[tuple[MarketRegime, str], dict]:
    """
    For each (regime, direction), run event study and return results.
    Returns dict keyed by (regime, direction).
    """
    results = {}

    # Unconditional baseline (all regimes combined)
    all_long_times = [_event_avail_at(ev, hyp_id) for ev in long_events]
    all_short_times = [_event_avail_at(ev, hyp_id) for ev in short_events]

    # Walk-forward on unconditional events
    wf_raw = _wf_sign_consistency(train_candles, all_long_times, all_short_times, horizons)

    for regime in ALL_REGIMES:
        r_long = filter_events_by_regime(long_events, avail_to_regime, hyp_id, regime)
        r_short = filter_events_by_regime(short_events, avail_to_regime, hyp_id, regime)
        r_long_times = [_event_avail_at(ev, hyp_id) for ev in r_long]
        r_short_times = [_event_avail_at(ev, hyp_id) for ev in r_short]

        # Multiple-testing tracker (per regime, all horizons × 2 directions)
        mt = MultipleTestingTracker()

        for direction, times in [("LONG", r_long_times), ("SHORT", r_short_times)]:
            n_ev = len(times)

            if n_ev >= 2:
                engine = EventStudyEngine(
                    event_times=times,
                    candles=train_candles,
                    horizons=horizons,
                    hypothesis_id=hyp_id,
                )
                study = engine.run()
            else:
                study = {}

            # Register tests for Holm correction
            for h in horizons:
                r = study.get(h)
                if r and r.valid_count >= 2 and r.p_value is not None:
                    mt.register(MultipleTestingRecord(
                        test_id=f"{hyp_id}-{direction}-H{h}",
                        hypothesis_id=hyp_id,
                        research_family=f"{hyp_id}-regime-{regime.value}",
                        p_value=r.p_value,
                        test_statistic=r.t_statistic,
                        n_observations=r.valid_count,
                    ))

            # Bootstrap CIs
            boot_cis: dict[int, object] = {}
            for h in horizons:
                if n_ev < 2:
                    continue
                raw = _collect_raw(train_candles, times, h, net_cost, direction)
                if len(raw) >= 4:
                    try:
                        ci = STATS.bootstrap_ci(raw, statistic="mean",
                                                 confidence=0.95, n_bootstrap=N_BOOTSTRAP)
                        boot_cis[h] = ci
                    except Exception:
                        pass

            # Holm significant set
            holm = mt.holm_sorted(alpha=ALPHA)
            holm_sig = {rec.test_id for rec, sig in holm if sig}

            # WF sign consistency for this direction
            wf_windows = wf_raw.get(direction, {})
            # Use unconditional WF sign rate as temporal stability proxy
            # (regime-specific WF would have too few events per window)
            wf_sign_rates: dict[str, float] = {}
            for d2 in ["LONG", "SHORT"]:
                window_means = []
                for h in horizons:
                    wlist = wf_raw.get(d2, {}).get(h, [])
                    window_means.extend([m for m in wlist if m is not None])
                if window_means:
                    expected_sign = 1.0 if d2 == "LONG" else -1.0
                    pos = sum(1 for m in window_means if m * expected_sign > 0)
                    wf_sign_rates[d2] = pos / len(window_means)
                else:
                    wf_sign_rates[d2] = 0.0

            verdict, reason = _verdict(
                n_events=n_ev,
                study_results=study,
                bootstrap_cis={"LONG": boot_cis, "SHORT": boot_cis},
                holm_significant=holm_sig,
                wf_sign_rates=wf_sign_rates,
                direction=direction,
                net_cost=net_cost,
                horizons=horizons,
                hyp_id=hyp_id,
            )

            results[(regime, direction)] = {
                "n_events": n_ev,
                "study": study,
                "boot_cis": boot_cis,
                "holm_sig": holm_sig,
                "wf_sign_rates": wf_sign_rates,
                "verdict": verdict,
                "reason": reason,
            }

    return results


# ── Matrix cell formatter ──────────────────────────────────────────────────────

VERDICT_ABBREV = {
    "SUPPORTED": "SUPP",
    "WEAK": "WEAK",
    "FRAGILE": "FRGL",
    "INCONCLUSIVE": "INCL",
    "REJECTED": "RJCT",
    "INSUFFICIENT_DATA": "INSF",
    "ERROR": "ERR ",
    "SKIP": "SKIP",
}


def _cell(long_v: str, short_v: str) -> str:
    la = VERDICT_ABBREV.get(long_v, "????")
    sa = VERDICT_ABBREV.get(short_v, "????")
    return f"L:{la}/S:{sa}"


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("=" * 78)
    print("REGIME-CONDITIONAL EVENT STUDY — TRAIN SPLIT")
    print("TRADING_DISABLED=True | Only TRAIN | No parameter changes | No HOLDOUT")
    print("=" * 78)
    print()

    # ── 1. Load dataset ──────────────────────────────────────────────────────
    print("[1] Loading BTCUSDT H4 dataset...")
    raw_dir = DATASETS_DIR / "raw" / "bybit" / SYMBOL / TIMEFRAME
    files = sorted(
        f for f in raw_dir.glob("*.json")
        if "2026-08-28" not in f.name and not f.name.startswith("oi_")
    ) if raw_dir.exists() else []
    if not files:
        print("  ERROR: No dataset. Run scripts/run_step_7_3.py first.")
        sys.exit(1)
    latest = files[-1]
    print(f"  File: {latest.name}")
    with open(latest) as fh:
        meta = json.load(fh)
    dataset_hash = meta.get("dataset_hash", "")
    if not dataset_hash.startswith(EXPECTED_HASH_PREFIX):
        print(f"  STOP: hash mismatch. Expected prefix: {EXPECTED_HASH_PREFIX}")
        sys.exit(1)
    all_candles = load_raw_json(latest)
    print(f"  Loaded {len(all_candles)} candles. Hash prefix: {dataset_hash[:16]}")

    # ── 2. TRAIN split only ──────────────────────────────────────────────────
    print("\n[2] Filtering to TRAIN split...")
    splits = make_splits(DATASET_ID, dataset_hash)
    train_candles = filter_by_split(all_candles, splits["train"])
    tr = splits["train"]
    print(f"  TRAIN: {tr.start.date()} → {tr.end.date()} = {len(train_candles)} candles")
    print("  OOS / HOLDOUT: NOT loaded.")
    if len(train_candles) < 200:
        print("  ERROR: Insufficient TRAIN candles.")
        sys.exit(1)

    # ── 3. Regime labeling ───────────────────────────────────────────────────
    print("\n[3] Running MarketRegimeDetector on TRAIN...")
    labeler = RegimeLabeler()
    regime_labels = labeler.label(train_candles)
    regime_dist = labeler.regime_distribution(regime_labels)
    avail_to_regime: dict[datetime, MarketRegime] = {
        lbl.close_time: lbl.regime for lbl in regime_labels
    }
    print(f"  Total bars: {len(regime_labels)}")
    for reg, cnt in sorted(regime_dist.items(), key=lambda x: -x[1]):
        pct = cnt / len(regime_labels) * 100
        print(f"    {reg.value:<12}: {cnt:>5} bars ({pct:.1f}%)")

    # ── 4. Load OI data for HYP-F ────────────────────────────────────────────
    oi_path = DATASETS_DIR / "raw" / "bybit" / SYMBOL / TIMEFRAME / "oi_2024-01-01_2026-09-30.json"
    oi_available = oi_path.exists()
    oi_series = {}
    oi_aligned: list | None = None
    if oi_available:
        print(f"\n[4] Loading OI data for HYP-F...")
        try:
            oi_series = load_oi_series(oi_path)
            oi_aligned = align_oi_to_candles(train_candles, oi_series)
            n_oi = sum(1 for x in oi_aligned if x is not None)
            print(f"  OI records: {len(oi_series)}, aligned: {n_oi}/{len(train_candles)}")
        except Exception as e:
            print(f"  WARNING: OI load failed: {e}")
            oi_available = False
    else:
        print(f"\n[4] OI file not found. HYP-F will be SKIP.")

    # ── 5. Detect events for all strategies ──────────────────────────────────
    print("\n[5] Detecting events on TRAIN split...")

    strategies: dict[str, dict] = {}

    try:
        la, sa = detect_a(train_candles)
        snap = snap_a(DATASET_ID, dataset_hash)
        strategies[HYP_A_001_ID] = dict(long=la, short=sa, horizons=HORIZONS_A,
            cost=COST_A, param_hash=snap.parameter_hash, dataset_hash=dataset_hash)
        print(f"  HYP-A: LONG={len(la)}, SHORT={len(sa)}")
    except Exception as e:
        print(f"  HYP-A: ERROR — {e}")
        strategies[HYP_A_001_ID] = dict(error=str(e))

    try:
        lb, sb = detect_b(train_candles)
        snap = snap_b(DATASET_ID, dataset_hash)
        strategies[HYP_B_001_ID] = dict(long=lb, short=sb, horizons=HORIZONS_B,
            cost=COST_B, param_hash=snap.parameter_hash, dataset_hash=dataset_hash)
        print(f"  HYP-B: LONG={len(lb)}, SHORT={len(sb)}")
    except Exception as e:
        print(f"  HYP-B: ERROR — {e}")
        strategies[HYP_B_001_ID] = dict(error=str(e))

    try:
        lc, sc = detect_c(train_candles)
        snap = snap_c(DATASET_ID, dataset_hash)
        strategies[HYP_C_001_ID] = dict(long=lc, short=sc, horizons=HORIZONS_C,
            cost=COST_C, param_hash=snap.parameter_hash, dataset_hash=dataset_hash)
        print(f"  HYP-C: LONG={len(lc)}, SHORT={len(sc)}")
    except Exception as e:
        print(f"  HYP-C: ERROR — {e}")
        strategies[HYP_C_001_ID] = dict(error=str(e))

    try:
        ld, sd = detect_d(train_candles)
        snap = snap_d(DATASET_ID, dataset_hash)
        strategies[HYP_D_001_ID] = dict(long=ld, short=sd, horizons=HORIZONS_D,
            cost=COST_D, param_hash=snap.parameter_hash, dataset_hash=dataset_hash)
        print(f"  HYP-D: LONG={len(ld)}, SHORT={len(sd)}")
    except Exception as e:
        print(f"  HYP-D: ERROR — {e}")
        strategies[HYP_D_001_ID] = dict(error=str(e))

    try:
        le, se = detect_e(train_candles)
        snap = snap_e(DATASET_ID, dataset_hash)
        strategies[HYP_E_001_ID] = dict(long=le, short=se, horizons=HORIZONS_E,
            cost=COST_E, param_hash=snap.parameter_hash, dataset_hash=dataset_hash)
        print(f"  HYP-E: LONG={len(le)}, SHORT={len(se)}")
    except Exception as e:
        print(f"  HYP-E: ERROR — {e}")
        strategies[HYP_E_001_ID] = dict(error=str(e))

    if oi_available and oi_aligned is not None:
        try:
            all_f = detect_f(train_candles, oi_aligned)
            lf = [e for e in all_f if e.direction == "LONG"]
            sf = [e for e in all_f if e.direction == "SHORT"]
            snap = snap_f(DATASET_ID, dataset_hash)
            strategies[HYP_F_001_ID] = dict(long=lf, short=sf, horizons=HORIZONS_F,
                cost=COST_F, param_hash=snap.parameter_hash, dataset_hash=dataset_hash)
            print(f"  HYP-F: LONG={len(lf)}, SHORT={len(sf)}")
        except Exception as e:
            print(f"  HYP-F: ERROR — {e}")
            strategies[HYP_F_001_ID] = dict(error=str(e))
    else:
        strategies[HYP_F_001_ID] = dict(skip="OI data not available")
        print(f"  HYP-F: SKIP (OI data not available)")

    # ── 6. Run regime-conditional event study ─────────────────────────────────
    print("\n[6] Running regime-conditional event study for each strategy...")
    all_results: dict[str, dict] = {}  # hyp_id → {(regime, dir): {...}}

    for hyp_id in STRATEGY_IDS:
        info = strategies.get(hyp_id, {})
        if "error" in info or "skip" in info:
            all_results[hyp_id] = {}
            continue
        print(f"  {hyp_id}...", end=" ", flush=True)
        try:
            res = run_one_strategy(
                hyp_id=hyp_id,
                long_events=info["long"],
                short_events=info["short"],
                train_candles=train_candles,
                avail_to_regime=avail_to_regime,
                horizons=info["horizons"],
                net_cost=info["cost"],
                dataset_id=DATASET_ID,
                dataset_hash=dataset_hash,
            )
            all_results[hyp_id] = res
            print("done")
        except Exception as e:
            all_results[hyp_id] = {}
            print(f"ERROR: {e}")

    # ── 7. Print detailed results ─────────────────────────────────────────────
    print()
    print("=" * 78)
    print("DETAILED RESULTS")
    print("=" * 78)

    for hyp_id in STRATEGY_IDS:
        info = strategies.get(hyp_id, {})
        res = all_results.get(hyp_id, {})

        print(f"\n{'─'*70}")
        if "skip" in info:
            print(f"{hyp_id}: SKIPPED — {info['skip']}")
            continue
        if "error" in info:
            print(f"{hyp_id}: ERROR — {info['error']}")
            continue

        horizons = info.get("horizons", [4, 8, 16, 32])
        cost = info.get("cost", Decimal("0.00105"))
        print(f"{hyp_id} | param_hash={info.get('param_hash','?')[:12]}...")
        print(f"  Total LONG: {len(info['long'])}, SHORT: {len(info['short'])}")

        for regime in ALL_REGIMES:
            for direction in ["LONG", "SHORT"]:
                cell = res.get((regime, direction))
                if cell is None:
                    continue
                n = cell["n_events"]
                v = cell["verdict"]
                rn = cell["reason"]
                print(f"  [{regime.value:<12} {direction:<5}] n={n:<4} → {v:<18} | {rn}")

    # ── 8. Verdict matrix ──────────────────────────────────────────────────────
    print()
    print("=" * 78)
    print("STRATEGY × REGIME VERDICT MATRIX (LONG / SHORT)")
    print("Verdicts: SUPPORTED | WEAK | FRAGILE | INCONCLUSIVE | REJECTED | INSUFFICIENT_DATA")
    print("=" * 78)

    regimes_order = [
        MarketRegime.TREND_UP,
        MarketRegime.TREND_DOWN,
        MarketRegime.RANGE,
        MarketRegime.HIGH_VOL,
        MarketRegime.LOW_VOL,
    ]
    reg_headers = ["TREND_UP", "TREND_DOWN", "RANGE", "HIGH_VOL", "LOW_VOL"]
    col_w = 20

    # Header
    header = f"{'':15}" + "".join(f"{h:>{col_w}}" for h in reg_headers)
    print(header)
    print("─" * (15 + col_w * len(regimes_order)))

    for hyp_id in STRATEGY_IDS:
        info = strategies.get(hyp_id, {})
        res = all_results.get(hyp_id, {})
        row = f"{hyp_id:<15}"
        for regime in regimes_order:
            if "skip" in info or "error" in info:
                cell = "SKIP"
            else:
                lv = res.get((regime, "LONG"), {}).get("verdict", "INSUFFICIENT_DATA")
                sv = res.get((regime, "SHORT"), {}).get("verdict", "INSUFFICIENT_DATA")
                cell = _cell(lv, sv)
            row += f"{cell:>{col_w}}"
        print(row)

    # ── 9. Event count matrix ──────────────────────────────────────────────────
    print()
    print("=" * 78)
    print("EVENT COUNTS BY REGIME (LONG + SHORT per cell)")
    print("=" * 78)
    header2 = f"{'':15}" + "".join(f"{h:>{col_w}}" for h in reg_headers)
    print(header2)
    print("─" * (15 + col_w * len(regimes_order)))

    for hyp_id in STRATEGY_IDS:
        info = strategies.get(hyp_id, {})
        res = all_results.get(hyp_id, {})
        row = f"{hyp_id:<15}"
        for regime in regimes_order:
            if "skip" in info or "error" in info:
                cell = "—"
            else:
                nl = res.get((regime, "LONG"), {}).get("n_events", 0)
                ns = res.get((regime, "SHORT"), {}).get("n_events", 0)
                cell = f"L:{nl}/S:{ns}"
            row += f"{cell:>{col_w}}"
        print(row)

    # ── 10. Summary of SUPPORTED / WEAK ───────────────────────────────────────
    print()
    print("=" * 78)
    print("SUMMARY")
    print("=" * 78)
    supported = []
    weak = []
    fragile = []
    insufficient = []

    for hyp_id in STRATEGY_IDS:
        info = strategies.get(hyp_id, {})
        res = all_results.get(hyp_id, {})
        if "skip" in info or "error" in info:
            continue
        for regime in regimes_order:
            for direction in ["LONG", "SHORT"]:
                v = res.get((regime, direction), {}).get("verdict", "INSUFFICIENT_DATA")
                if v == "SUPPORTED":
                    supported.append(f"{hyp_id} / {regime.value} / {direction}")
                elif v == "WEAK":
                    weak.append(f"{hyp_id} / {regime.value} / {direction}")
                elif v == "FRAGILE":
                    fragile.append(f"{hyp_id} / {regime.value} / {direction}")
                elif v == "INSUFFICIENT_DATA":
                    insufficient.append(f"{hyp_id} / {regime.value} / {direction}")

    print(f"\nSUPPORTED ({len(supported)}):")
    for s in supported: print(f"  ✓ {s}")
    if not supported: print("  (none)")

    print(f"\nWEAK ({len(weak)}):")
    for s in weak: print(f"  ~ {s}")
    if not weak: print("  (none)")

    print(f"\nFRAGILE ({len(fragile)}):")
    for s in fragile: print(f"  ! {s}")
    if not fragile: print("  (none)")

    print(f"\nINSUFFICIENT_DATA ({len(insufficient)}):")
    for s in insufficient[:10]: print(f"  - {s}")
    if len(insufficient) > 10: print(f"  ... and {len(insufficient)-10} more")

    # ── 11. Reproducibility check ──────────────────────────────────────────────
    print()
    print("=" * 78)
    print("REPRODUCIBILITY AUDIT")
    print("=" * 78)
    for hyp_id in STRATEGY_IDS:
        info = strategies.get(hyp_id, {})
        if "skip" in info or "error" in info:
            continue
        print(f"  {hyp_id}: param_hash={info.get('param_hash','?')[:20]} | dataset_hash_prefix={info.get('dataset_hash','?')[:16]}")

    # ── 12. Transition readiness ───────────────────────────────────────────────
    print()
    print("=" * 78)
    print("VALIDATION READINESS (per RESEARCH PROTOCOL)")
    print("=" * 78)
    validated_ready = []
    for hyp_id in STRATEGY_IDS:
        info = strategies.get(hyp_id, {})
        res = all_results.get(hyp_id, {})
        if "skip" in info or "error" in info:
            continue
        has_supported = any(
            res.get((r, d), {}).get("verdict") in ("SUPPORTED", "WEAK")
            for r in regimes_order for d in ["LONG", "SHORT"]
        )
        if has_supported:
            validated_ready.append(hyp_id)

    if validated_ready:
        print(f"\nStrategies with TRAIN-level evidence (SUPPORTED or WEAK):")
        for h in validated_ready:
            print(f"  → {h}: eligible for VALIDATION (do NOT advance yet — document first)")
    else:
        print("\nNo strategy reached SUPPORTED or WEAK on TRAIN.")
        print("Recommendation: DO NOT advance to VALIDATION.")

    print()
    print("NEXT STEPS:")
    print("  1. Review this report.")
    print("  2. Document TRAIN findings in docs/regime_research/")
    print("  3. Freeze parameters (already frozen in each hyp_*.py).")
    print("  4. If SUPPORTED/WEAK: create TRAIN_REPORT.md with full evidence.")
    print("  5. ONLY THEN proceed to VALIDATION.")
    print("  6. DO NOT use HOLDOUT.")
    print()
    print("=" * 78)
    print("REGIME TRAIN RESEARCH COMPLETE.")
    print("STOPPED. Not proceeding to VALIDATION.")
    print("=" * 78)


if __name__ == "__main__":
    main()
