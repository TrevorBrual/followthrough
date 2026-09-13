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
python src/orchestrator.py
```

## Reliability

```
python eval/run_eval.py
```

Runs the extractor against `eval/transcripts/*` and compares against the answer
keys, printing a pass rate.

<!-- Pass rate: fill in after the eval harness is populated -->
