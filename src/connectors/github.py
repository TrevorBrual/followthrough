"""GitHub connector: one issue per action item. Owner: Integrator B."""

import os

from ._common import dry_run, owner_label, request_with_retry


def _body(item: dict) -> str:
    due = item.get("due_date") or "no deadline set"
    return (
        f"**Owner:** {owner_label(item)}\n"
        f"**Due:** {due}\n"
        f"**Priority:** {item['priority']}\n\n"
        "_Opened automatically from a meeting transcript by followthrough._"
    )


def create_issue(item: dict) -> dict:
    """Open one GitHub issue. Returns {ok, url} — url is None in dry-run."""
    if dry_run():
        print(f"  [dry-run] GitHub: would open issue -> {item['task']!r}")
        return {"ok": True, "url": None}

    repo = os.environ["GITHUB_REPO"]
    response = request_with_retry(
        "POST",
        f"https://api.github.com/repos/{repo}/issues",
        headers={
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github+json",
        },
        json={"title": item["task"], "body": _body(item)},
    )
    return {"ok": True, "url": response.json().get("html_url")}
