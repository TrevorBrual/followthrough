"""Slack connector: one recap message per run. Owner: Integrator B."""

import os

from ._common import dry_run, owner_label, request_with_retry


def _format(items: list[dict], failed: int = 0) -> str:
    # An empty recap means two very different things: the meeting genuinely had
    # no action items, or it had some and we couldn't save any. Saying "none
    # found" for the second is a lie, and it's the case that shows up when a
    # token expires mid-run.
    if not items and not failed:
        return "*Meeting recap:* no action items found in this transcript."

    if items:
        lines = [f"*Meeting recap:* {len(items)} action item(s) created."]
        for item in items:
            due = item.get("due_date") or "no deadline"
            lines.append(f"• {item['task']} — {owner_label(item)} ({due}, {item['priority']})")
    else:
        lines = ["*Meeting recap:* action items were found but none could be saved."]

    if failed:
        lines.append(f"_{failed} item(s) failed to save — check the run log._")
    return "\n".join(lines)


def post_recap(items: list[dict], failed: int = 0) -> dict:
    """Post one summary message listing everything created.

    `failed` is the number of extracted items that did not make it to any app,
    so the recap can't imply a clean run when writes were dropped.
    """
    text = _format(items, failed)

    if dry_run():
        print("  [dry-run] Slack: would post ->")
        print("\n".join(f"    {line}" for line in text.splitlines()))
        return {"ok": True}

    request_with_retry(
        "POST", os.environ["SLACK_WEBHOOK_URL"], json={"text": text}
    )
    return {"ok": True}
