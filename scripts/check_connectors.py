"""Setup checklist as a script: prove one real call reaches each app.

Section 5 of the build plan - nobody moves past setup until every service
answers. Owner: Integrator B.

    python scripts/check_connectors.py          # check config only, no API calls
    python scripts/check_connectors.py --live   # actually write to all three

--live creates a real Notion row, a real GitHub issue and a real Slack
message, each labelled as a setup test. Delete them when you're done.

This calls the same add_task / create_issue / post_recap the orchestrator
calls, deliberately. A smoke test that rebuilds the requests itself proves
the smoke test works, not the connectors.
"""

import argparse
import os
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import requests  # noqa: E402

from src.connectors import _common  # noqa: E402,F401  (loads .env on import)
from src.connectors.github import create_issue  # noqa: E402
from src.connectors.notion import NOTION_VERSION, add_task  # noqa: E402
from src.connectors.slack import post_recap  # noqa: E402

TEST_ITEM = {
    "task": "followthrough setup check - safe to delete",
    "owner": "Setup Check",
    "due_date": "2026-09-13",
    "priority": "low",
}

# What notion.py's _properties() writes. A mismatch here is a 400 on every
# single row, so it is worth catching before the demo rather than during it.
REQUIRED_NOTION_PROPERTIES = {
    "Task": "title",
    "Owner": "rich_text",
    "Due": "date",
    "Priority": "select",
}


def _missing(names: list[str]) -> list[str]:
    return [name for name in names if not os.getenv(name)]


def _notion_property_problems(props: dict) -> list[str]:
    problems = []
    for name, expected in REQUIRED_NOTION_PROPERTIES.items():
        actual = props.get(name)
        if actual is None:
            found = ", ".join(sorted(props)) or "none"
            problems.append(f"no {name!r} property in the database (found: {found})")
        elif actual.get("type") != expected:
            problems.append(
                f"{name!r} is a {actual.get('type')} property, connector expects {expected}"
            )
    return problems


def check_notion(live: bool) -> tuple[bool, str]:
    missing = _missing(["NOTION_API_KEY", "NOTION_DATABASE_ID"])
    if missing:
        return False, f"missing in .env: {', '.join(missing)}"
    if not live:
        return True, "config present (run with --live to write a row)"

    database_id = os.environ["NOTION_DATABASE_ID"]
    response = requests.get(
        f"https://api.notion.com/v1/databases/{database_id}",
        headers={
            "Authorization": f"Bearer {os.environ['NOTION_API_KEY']}",
            "Notion-Version": NOTION_VERSION,
        },
        timeout=15,
    )
    if response.status_code == 401:
        return False, "Notion rejected NOTION_API_KEY (401)"
    if response.status_code == 404:
        return False, (
            "Notion returned 404. Either NOTION_DATABASE_ID is wrong, or the "
            "database is not shared with your integration - open the database, "
            "... menu -> Connections -> add it. This is the usual one."
        )
    if response.status_code >= 400:
        return False, f"{response.status_code} reading the database: {response.text[:300]}"

    problems = _notion_property_problems(response.json().get("properties", {}))
    if problems:
        return False, "; ".join(problems)

    return True, f"row created: {add_task(TEST_ITEM)['url']}"


def check_github(live: bool) -> tuple[bool, str]:
    missing = _missing(["GITHUB_TOKEN", "GITHUB_REPO"])
    if missing:
        return False, f"missing in .env: {', '.join(missing)}"

    repo = os.environ["GITHUB_REPO"]
    if repo.count("/") != 1 or repo == "owner/repo":
        return False, f"GITHUB_REPO should look like 'owner/repo', got {repo!r}"
    if not live:
        return True, "config present (run with --live to open an issue)"

    response = requests.get(
        f"https://api.github.com/repos/{repo}",
        headers={
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github+json",
        },
        timeout=15,
    )
    if response.status_code == 401:
        return False, "GitHub rejected GITHUB_TOKEN (401) - expired or mistyped"
    if response.status_code == 404:
        return False, (
            f"GitHub cannot see {repo} (404). Either the name is wrong or the "
            "fine-grained token does not list this repository under its access."
        )
    if response.status_code >= 400:
        return False, f"{response.status_code} reading the repo: {response.text[:300]}"
    if response.json().get("has_issues") is False:
        return False, f"Issues are disabled on {repo} (Settings -> Features -> Issues)"

    return True, f"issue opened: {create_issue(TEST_ITEM)['url']}"


def check_slack(live: bool) -> tuple[bool, str]:
    missing = _missing(["SLACK_WEBHOOK_URL"])
    if missing:
        return False, f"missing in .env: {', '.join(missing)}"
    if not os.environ["SLACK_WEBHOOK_URL"].startswith("https://hooks.slack.com/"):
        return False, "SLACK_WEBHOOK_URL is not an https://hooks.slack.com/... webhook"
    if not live:
        return True, "config present (run with --live to post a message)"

    post_recap([TEST_ITEM])
    return True, "message posted to the webhook's channel"


CHECKS = (("Notion", check_notion), ("GitHub", check_github), ("Slack", check_slack))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="make real API calls (writes a row, an issue and a message)",
    )
    args = parser.parse_args()

    # The connectors read DRY_RUN at call time, so set it explicitly here
    # instead of inheriting whatever happens to be in .env.
    os.environ["DRY_RUN"] = "false" if args.live else "true"

    print("LIVE - writing to all three apps\n" if args.live
          else "CONFIG CHECK - no API calls. Use --live to actually write.\n")

    failures = 0
    for name, check in CHECKS:
        try:
            ok, detail = check(args.live)
        except Exception as exc:  # a connector raised rather than answering
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        print(f"{'PASS' if ok else 'FAIL'}  {name:<7} {detail}")
        failures += not ok

    print()
    if failures:
        print(f"{failures} of {len(CHECKS)} services not ready. Fix these before building on them.")
        return 1

    print("All three services answered.")
    if args.live:
        print("Delete the test row, issue and message before the demo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
