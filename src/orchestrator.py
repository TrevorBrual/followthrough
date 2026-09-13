"""Glue: transcript -> extraction -> Notion + GitHub -> Slack recap.

Run with `python -m src.orchestrator` (reads a transcript on stdin, or uses the
sample one). A failure in a single connector is recorded and the run continues,
so one bad row never costs you the rest of the meeting.
"""

import sys

from .connectors._common import dry_run
from .connectors.github import create_issue
from .connectors.notion import add_task
from .connectors.slack import post_recap
from .extract import SAMPLE_TRANSCRIPT, extract


def run(transcript: str) -> dict:
    print(f"Mode: {'DRY RUN' if dry_run() else 'LIVE'}\n")

    # Guarded because this is the one call that can take the whole run down:
    # no key, no network, API having a bad day. A traceback on screen is a
    # worse answer than saying what failed and that nothing was written.
    try:
        items = extract(transcript)
    except Exception as exc:
        print(f"Extraction failed: {type(exc).__name__}: {exc}")
        print("Nothing was written to any app.")
        return {
            "items": [],
            "created": [],
            "dropped": [],
            "failures": [{"stage": "extract", "task": None, "error": str(exc)}],
        }

    print(f"Extracted {len(items)} action item(s).\n")

    created, dropped, failures = [], [], []
    for item in items:
        print(f"- {item['task']}")
        item_ok = True
        for name, call in (("notion", add_task), ("github", create_issue)):
            try:
                call(item)
            except Exception as exc:
                item_ok = False
                failures.append({"stage": name, "task": item["task"], "error": str(exc)})
                print(f"  [error] {name}: {exc}")
        (created if item_ok else dropped).append(item)

    try:
        post_recap(created, failed=len(dropped))
    except Exception as exc:
        failures.append({"stage": "slack", "task": None, "error": str(exc)})
        print(f"  [error] slack: {exc}")

    print(f"\nDone. {len(created)} created, {len(dropped)} dropped, {len(failures)} failure(s).")
    return {"items": items, "created": created, "dropped": dropped, "failures": failures}


if __name__ == "__main__":
    transcript = sys.stdin.read() if not sys.stdin.isatty() else SAMPLE_TRANSCRIPT
    result = run(transcript)
    sys.exit(1 if result["failures"] else 0)
