"""
STEP 7.4 — HYP-B research entry point.

HYP-B: Breakout + Retest

This script is intentionally a research entry point only.
It does NOT access OOS or HOLDOUT.

Workflow:
    DATA -> HYPOTHESIS -> TRAIN -> FREEZE -> VALIDATION

HYP-B parameters must be explicitly defined before validation.
No OOS/HOLDOUT tuning is allowed.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs" / "research" / "HYP-A-001_DECISION.md"


def main() -> None:
    print("=" * 60)
    print("STEP 7.4 — HYP-B: BREAKOUT + RETEST")
    print("=" * 60)
    print()
    print("Previous candidate:")
    print("  HYP-A-001 = WEAK")
    print("  Decision  = DO NOT ADVANCE TO OOS")
    print()
    print("Current candidate:")
    print("  HYP-B = Breakout + Retest")
    print()
    print("Allowed stages:")
    print("  DATA -> HYPOTHESIS -> TRAIN -> FREEZE -> VALIDATION")
    print()
    print("Protected stages:")
    print("  OOS      = NOT TOUCHED")
    print("  HOLDOUT  = NOT TOUCHED")
    print()
    print("This is an explicit research entry point.")
    print("No strategy parameters are silently selected here.")
    print("No OOS/HOLDOUT data is loaded here.")
    print()
    print("NEXT: define HYP-B event specification before implementation.")


if __name__ == "__main__":
    main()
