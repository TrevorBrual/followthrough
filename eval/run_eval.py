#!/usr/bin/env python3
"""
Meeting-to-Action reliability evaluation runner.

Usage:
    python3 eval/run_eval.py

Loads eval/cases.json, runs each transcript through the pluggable extractor
(eval/extractor_adapter.py -- real extractor if plugged in, otherwise the
mock stub), scores the result against the known-correct answer key, and
prints a terminal reliability report.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.evaluator import CaseResult, FieldTally, evaluate_case
from eval.extractor_adapter import run_extractor

DEFAULT_CASES_PATH = Path(__file__).resolve().parent / "cases.json"


def cases_path() -> Path:
    """Optional argv override so the same scorer can run the held-out set:
    python -m eval.run_eval eval/holdout.json"""
    return Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CASES_PATH


def load_cases() -> dict:
    with open(cases_path(), "r", encoding="utf-8") as f:
        return json.load(f)


def mark(ok: bool) -> str:
    return "✓" if ok else "✗"


def print_report(results: list[CaseResult]) -> None:
    header = f"{'Case':<28} {'Count':^7} {'Owner':^7} {'Due Date':^9} {'Task':^6} {'Result':<6}"
    print("Meeting-to-Action Reliability Evaluation\n")
    print(header)
    print("-" * len(header))

    for r in results:
        print(
            f"{r.case_id:<28} {mark(r.count_ok):^7} {mark(r.owner_ok):^7} "
            f"{mark(r.due_ok):^9} {mark(r.task_ok):^6} {'PASS' if r.passed else 'FAIL':<6}"
        )

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    pass_rate = (passed / total * 100) if total else 0.0

    task_tally, owner_tally, due_tally, priority_tally = FieldTally(), FieldTally(), FieldTally(), FieldTally()
    for r in results:
        for item in r.item_scores:
            task_tally.record(item.task_ok)
            owner_tally.record(item.owner_ok)
            due_tally.record(item.due_ok)
            if item.priority_ok is not None:
                priority_tally.record(item.priority_ok)

    print(f"\nOverall: {passed}/{total} passed")
    print(f"Pass rate: {pass_rate:.1f}%\n")

    def pct(tally: FieldTally) -> str:
        return f"{(tally.correct / tally.total * 100):.0f}%" if tally.total else "n/a"

    print(f"Task accuracy: {pct(task_tally)}")
    print(f"Owner accuracy: {pct(owner_tally)}")
    print(f"Due-date accuracy: {pct(due_tally)}")
    print(f"Priority accuracy: {pct(priority_tally)}")

    failures = [r for r in results if not r.passed]
    if failures:
        print("\nFailures:")
        for r in failures:
            print(f"\nFAIL: {r.case_id}")
            for reason in r.reasons:
                print(f"  - {reason}")


def main() -> int:
    data = load_cases()
    default_reference_date = data.get("reference_date")
    cases = data["cases"]

    results = []
    for case in cases:
        reference_date = case.get("reference_date", default_reference_date)
        actual = run_extractor(case["transcript"], reference_date=reference_date)
        results.append(evaluate_case(case, actual))

    print_report(results)

    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
