# followthrough

Turning raw meeting transcript into completed action items across Notion, GitHub, and Slack, with a dry-run mode and an eval harness that reports a live pass rate.

## Architecture

```
transcript ──► LLM extraction ──► JSON [{task, owner, due_date, priority}, ...]
                                        │
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
              Notion row          GitHub issue         (after both)
                    │                   │                   │
                    └───────────────────┴───────► Slack recap
```

| Piece | File | Owner |
| --- | --- | --- |
| LLM extraction + JSON schema | `src/extract.py` | Integrator A |
| `add_task(item)` → Notion | `src/connectors/notion.py` | Integrator B |
| `create_issue(item)` → GitHub | `src/connectors/github.py` | Integrator B |
| `post_recap(items)` → Slack | `src/connectors/slack.py` | Integrator B |
| Glue | `src/orchestrator.py` | shared |
| Test transcripts + pass rate | `eval/` | Reliability lead |

## Setup

1. `pip install -r requirements.txt`
2. `cp .env.example .env` and fill in keys:
   - `ANTHROPIC_API_KEY` — Anthropic key
   - `NOTION_API_KEY` / `NOTION_DATABASE_ID` — create an integration, share your
     tracker database with it
   - `GITHUB_TOKEN` / `GITHUB_REPO` — fine-grained PAT with `Issues: write` on a
     throwaway repo
   - `SLACK_WEBHOOK_URL` — an Incoming Webhook for a test channel
3. Leave `DRY_RUN=true` until every connector is verified — with it on, each
   connector logs "would create X" instead of calling the real API.
4. Sanity-check each service independently before running the full pipeline
   (one test completion, one curl to the Slack webhook, one test GitHub issue,
   one test Notion row).

## Run

```
python -m src.orchestrator              # uses the built-in sample transcript
cat meeting.txt | python -m src.orchestrator
```

Extraction alone, to check the JSON in isolation:

```
python -m src.extract
```

## Reliability

```
python -m eval.run_eval
```

Runs the 12 cases in `eval/cases.json` through the extractor and reports a pass
rate plus per-field accuracy for task, owner, due date and priority. The harness
only calls the extractor, so it never touches Notion, GitHub or Slack.

It prints which extractor it used on the first line. Without a working
`ANTHROPIC_API_KEY` it falls back to a rule-based mock and says so — a pass rate
from a mock run tells you nothing about real extraction quality.

See `eval/README.md` for how cases and scoring work.

### Shape the extractor returns

```python
{"task": "fix the login bug", "owner": "Sarah", "due_date": "2026-09-18", "priority": "medium"}
```

`owner` and `due_date` are `None` when the meeting didn't state one. The
connectors show an absent owner as "Unassigned"; the data itself stays `None`.

<!-- Pass rate: fill in after the eval harness is populated -->
