"""Eval harness: run every case through the extractor and print a pass rate.

Owner: Reliability lead. Add cases as JSON files in eval/cases/ — each needs a
transcript and an expected {count, owners}. Target is 8-12 cases including the
hard ones (no action items, ambiguous owner, two tasks in one sentence).

Run with `python -m eval.run_eval`. Forces DRY_RUN so no app is ever touched.
"""

import json
import os
import pathlib
import sys
from collections import Counter

os.environ["DRY_RUN"] = "true"

from src.extract import extract  # noqa: E402  (must follow the DRY_RUN guard)

CASES_DIR = pathlib.Path(__file__).parent / "cases"


def check(case: dict) -> tuple[bool, str]:
    """Compare extracted items against the answer key. Returns (passed, detail)."""
    items = extract(case["transcript"], case.get("meeting_date"))
    expected = case["expected"]

    got_count = len(items)
    if got_count != expected["count"]:
        return False, f"expected {expected['count']} item(s), got {got_count}"

    got_owners = Counter(item["owner"] for item in items)
    want_owners = Counter(expected["owners"])
    if got_owners != want_owners:
        return False, f"owners {sorted(got_owners.elements())} != {sorted(want_owners.elements())}"

    return True, ""


def main() -> int:
    cases = sorted(CASES_DIR.glob("*.json"))
    if not cases:
        print(f"No cases found in {CASES_DIR}")
        return 1

    passed = 0
    for path in cases:
        case = json.loads(path.read_text())
        try:
            ok, detail = check(case)
        except Exception as exc:
            ok, detail = False, f"error: {exc}"

        passed += ok
        print(f"{'PASS' if ok else 'FAIL'}  {case['name']}")
        if not ok:
            print(f"      {detail}")

    rate = passed / len(cases) * 100
    print(f"\n{passed}/{len(cases)} passed ({rate:.0f}%)")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
