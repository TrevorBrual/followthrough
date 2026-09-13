"""Connector tests - payload shaping, dry-run gating and retry behaviour.

Owner: Integrator B. Stdlib unittest so there is no new dependency to install
on hackathon day. No network: every test either runs in dry-run or patches
requests.request.

    python -m unittest discover -s tests -v
"""

import os
import sys
import pathlib
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.connectors import _common, github, notion, slack  # noqa: E402

FULL = {
    "task": "fix the mobile Safari signup 500",
    "owner": "Marcus",
    "due_date": "2026-09-17",
    "priority": "high",
}
BARE = {"task": "clean up the old staging bucket", "owner": None,
        "due_date": None, "priority": "low"}


class DryRunGate(unittest.TestCase):
    """DRY_RUN=true must mean no connector reaches the network."""

    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"DRY_RUN": "true"})
        self.env.start()
        self.addCleanup(self.env.stop)
        # Any HTTP attempt at all should fail the test loudly.
        boom = mock.patch.object(
            _common, "requests",
            **{"request.side_effect": AssertionError("dry-run made a network call")},
        )
        boom.start()
        self.addCleanup(boom.stop)

    def test_notion_returns_ok_without_calling(self):
        self.assertEqual(notion.add_task(FULL), {"ok": True, "url": None})

    def test_github_returns_ok_without_calling(self):
        self.assertEqual(github.create_issue(FULL), {"ok": True, "url": None})

    def test_slack_returns_ok_without_calling(self):
        self.assertEqual(slack.post_recap([FULL]), {"ok": True})

    def test_dry_run_defaults_on_when_unset(self):
        with mock.patch.dict(os.environ, clear=False) as env:
            os.environ.pop("DRY_RUN", None)
            self.assertTrue(_common.dry_run())

    def test_dry_run_off_only_for_explicit_false(self):
        for value, expected in (("false", False), ("0", False), ("no", False),
                                ("true", True), ("1", True)):
            with mock.patch.dict(os.environ, {"DRY_RUN": value}):
                self.assertIs(_common.dry_run(), expected, f"DRY_RUN={value}")


class NotionProperties(unittest.TestCase):
    """The row payload has to match the database schema exactly."""

    def test_shapes_each_property_type(self):
        props = notion._properties(FULL)
        self.assertEqual(props["Task"]["title"][0]["text"]["content"], FULL["task"])
        self.assertEqual(props["Owner"]["rich_text"][0]["text"]["content"], "Marcus")
        self.assertEqual(props["Priority"]["select"]["name"], "high")
        self.assertEqual(props["Due"]["date"]["start"], "2026-09-17")

    def test_omits_due_entirely_when_there_is_no_deadline(self):
        # Sending {"date": {"start": None}} is a 400; the key must be absent.
        self.assertNotIn("Due", notion._properties(BARE))

    def test_unowned_task_gets_a_placeholder_not_null(self):
        props = notion._properties(BARE)
        self.assertEqual(props["Owner"]["rich_text"][0]["text"]["content"], "Unassigned")


class GitHubIssue(unittest.TestCase):
    def test_body_carries_owner_due_and_priority(self):
        body = github._body(FULL)
        self.assertIn("Marcus", body)
        self.assertIn("2026-09-17", body)
        self.assertIn("high", body)

    def test_missing_deadline_reads_as_words_not_none(self):
        self.assertIn("no deadline set", github._body(BARE))
        self.assertNotIn("None", github._body(BARE))


class SlackRecap(unittest.TestCase):
    def test_one_bullet_per_item(self):
        text = slack._format([FULL, BARE])
        self.assertIn("2 action item(s)", text)
        self.assertEqual(text.count("•"), 2)

    def test_empty_list_says_so_without_inventing_tasks(self):
        self.assertIn("no action items", slack._format([]))

    def test_bare_item_renders_without_none(self):
        self.assertNotIn("None", slack._format([BARE]))


class RetryPolicy(unittest.TestCase):
    """request_with_retry is the only thing standing between us and a flaky
    demo, so pin down exactly what it retries."""

    def setUp(self):
        sleep = mock.patch.object(_common.time, "sleep")  # keep tests instant
        sleep.start()
        self.addCleanup(sleep.stop)

    @staticmethod
    def _response(status, text="{}"):
        return mock.Mock(status_code=status, text=text)

    def test_retries_a_429_then_succeeds(self):
        calls = [self._response(429), self._response(200)]
        with mock.patch.object(_common.requests, "request", side_effect=calls) as req:
            result = _common.request_with_retry("POST", "https://example.test")
        self.assertEqual(req.call_count, 2)
        self.assertEqual(result.status_code, 200)

    def test_gives_up_after_the_attempt_budget(self):
        with mock.patch.object(
            _common.requests, "request", return_value=self._response(503)
        ) as req:
            with self.assertRaises(_common.requests.HTTPError):
                _common.request_with_retry("POST", "https://example.test", attempts=3)
        self.assertEqual(req.call_count, 3)

    def test_does_not_retry_a_client_error(self):
        with mock.patch.object(
            _common.requests, "request", return_value=self._response(400)
        ) as req:
            with self.assertRaises(_common.requests.HTTPError):
                _common.request_with_retry("POST", "https://example.test")
        self.assertEqual(req.call_count, 1)

    def test_error_message_includes_the_response_body(self):
        body = '{"message":"Due is not a property that exists"}'
        with mock.patch.object(
            _common.requests, "request", return_value=self._response(400, body)
        ):
            with self.assertRaises(_common.requests.HTTPError) as caught:
                _common.request_with_retry("POST", "https://example.test")
        self.assertIn("Due is not a property that exists", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
