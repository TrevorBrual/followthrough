# followthrough

Turning raw meeting transcript into completed action items across Notion, GitHub, and Slack, with a dry-run mode and an eval harness that reports a live pass rate.

## How well does it work?

Extraction is the step everything downstream trusts, so it is the step we
measured. Three separate sets, reported separately because they answer
different questions:

| Set | Cases | Result | What it tells you |
| --- | --- | --- | --- |
| dev | 12 | 12/12 | Tuned against these. A training score. |
| holdout | 8 | 8/8 | Written after the prompt froze. |
| blind | 10 | 8-9/10 | Frozen in git before it ever ran. |

The blind number is the one that counts, and it moves between runs on identical
code, so treat any single pass rate as a sample rather than a measurement.

**[RELIABILITY.md](RELIABILITY.md)** has the methodology, both documented
failure cases, the guardrails, and what we think this does not prove.

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
| LLM extraction + JSON schema | `src/extract.py` | Carl |
| `add_task(item)` → Notion | `src/connectors/notion.py` | Trevor |
| `create_issue(item)` → GitHub | `src/connectors/github.py` | Trevor |
| `post_recap(items)` → Slack | `src/connectors/slack.py` | Trevor |
| Glue | `src/orchestrator.py` | shared |
| Test transcripts + pass rate | `eval/` | Michali |

## Setup

1. `pip install -r requirements.txt`
2. `cp .env.example .env` and fill in keys:
   - `ANTHROPIC_API_KEY` — Anthropic key
   - `NOTION_API_KEY` / `NOTION_DATABASE_ID` — create an integration, share your
     tracker database with it, and give the database exactly these properties:

     | Property | Type |
     | --- | --- |
     | `Task` | title |
     | `Owner` | rich_text |
     | `Due` | date |
     | `Priority` | select |

     Names and types both have to match — anything else is a 400 on every
     write. Build the database to match this rather than renaming the code.
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

Run from the repo root. `.env` is loaded relative to the repo, not your shell,
so this works from anywhere — but the `python -m` form needs the root on the
path.

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

### Current results

Claude Opus 5, measured 2026-09-13:

| Set | Cases | Pass rate |
| --- | --- | --- |
| `eval/cases.json` | 12 | 12/12 (100%) |
| `eval/holdout.json` | 8 | 8/8 (100%) |

Per-field accuracy is 100% on both for task, owner, due date and priority.

The honest caveat: the prompt was tuned against `cases.json`, so that 12/12 is a
training score. `holdout.json` is 8 transcripts written after the prompt was
frozen and never used to tune it — that 8/8 is the number that says it
generalizes. Run both:

```
python -m eval.run_eval
python -m eval.run_eval eval/holdout.json
```

Known limits: 20 cases is a small sample, every case is English and
single-meeting, and the answer keys encode one reasonable reading of each
transcript — "is this urgent or just important" is a judgement call a human
would sometimes make differently.
