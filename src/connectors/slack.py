"""Slack connector: one recap message per run. Owner: Integrator B."""

import os

from ._common import dry_run, request_with_retry


def _format(items: list[dict]) -> str:
    if not items:
        return "*Meeting recap:* no action items found in this transcript."

    lines = [f"*Meeting recap:* {len(items)} action item(s) created."]
    for item in items:
        due = item.get("due_date") or "no deadline"
        lines.append(f"• {item['task']} — {item['owner']} ({due}, {item['priority']})")
    return "\n".join(lines)


def post_recap(items: list[dict]) -> dict:
    """Post one summary message listing everything created."""
    text = _format(items)

    if dry_run():
        print("  [dry-run] Slack: would post ->")
        print("\n".join(f"    {line}" for line in text.splitlines()))
        return {"ok": True}

    request_with_retry(
        "POST", os.environ["SLACK_WEBHOOK_URL"], json={"text": text}
    )
    return {"ok": True}
