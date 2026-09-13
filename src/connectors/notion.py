"""Tracker connector: one Notion row per action item. Owner: Integrator B.

Assumes the target database has properties: Task (title), Owner (rich_text),
Due (date), Priority (select). Adjust PROPERTIES if your database differs.
"""

import os

from ._common import dry_run, request_with_retry

NOTION_API = "https://api.notion.com/v1/pages"
NOTION_VERSION = "2022-06-28"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['NOTION_API_KEY']}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _properties(item: dict) -> dict:
    props = {
        "Task": {"title": [{"text": {"content": item["task"]}}]},
        "Owner": {"rich_text": [{"text": {"content": item["owner"]}}]},
        "Priority": {"select": {"name": item["priority"]}},
    }
    if item.get("due_date"):
        props["Due"] = {"date": {"start": item["due_date"]}}
    return props


def add_task(item: dict) -> dict:
    """Create one Notion row. Returns {ok, url} — url is None in dry-run."""
    if dry_run():
        print(f"  [dry-run] Notion: would add row -> {item['task']!r} ({item['owner']})")
        return {"ok": True, "url": None}

    response = request_with_retry(
        "POST",
        NOTION_API,
        headers=_headers(),
        json={
            "parent": {"database_id": os.environ["NOTION_DATABASE_ID"]},
            "properties": _properties(item),
        },
    )
    return {"ok": True, "url": response.json().get("url")}
