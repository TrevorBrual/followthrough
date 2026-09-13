# Reliability & Evaluation Brief

## 1. What we evaluate

The riskiest step is the first one: turning messy spoken language into structured
action items. Everything downstream is a side effect of it — each item becomes a
Notion row, a GitHub issue, and a line in a Slack recap. A hallucinated task
doesn't stay a string in a JSON blob; it becomes a real issue in someone's
tracker. So extraction is what we test.

The schema is the contract between extraction and every connector
(`src/extract.py`, enforced as a Pydantic model):

| Field | Type | Meaning |
| --- | --- | --- |
| `task` | `str` (required) | Imperative phrase — no owner name, no deadline or urgency wording |
| `owner` | `str \| None` | Name as used in the transcript; `null` when nobody claimed it |
| `due_date` | `str \| None` | ISO `YYYY-MM-DD`; `null` when the meeting set no deadline |
| `priority` | `"high" \| "medium" \| "low"` | Constrained by the schema; defaults to `medium` |

Nothing in `eval/` imports a connector, so scoring runs cannot write to Notion,
GitHub, or Slack.

## 2. Evaluation methodology

**Storage.** Two JSON files, each with a `reference_date` and a list of cases
(`id`, `description`, `transcript`, `expected` answer key); a case may override the
reference date, so relative-date tests are deterministic.

**Running.** One scorer, both sets:

```
python -m eval.run_eval                      # dev:     eval/cases.json  (12 cases)
python -m eval.run_eval eval/holdout.json    # holdout: eval/holdout.json (8 cases)
```

`eval/extractor_adapter.py` calls `src.extract.extract_actions(transcript,
reference_date)` and prints which extractor ran on the first line. If the real one
can't be imported it falls back to a rule-based mock and says so loudly.

**Checked.** Item count per case; `task`, `owner`, `due_date`, `priority` per item
(priority only where the key specifies one). Text is lowercased,
punctuation-stripped, whitespace-collapsed; dates are normalized to ISO from
several formats. Task text matches on character similarity at a **0.6 threshold** —
casing and small phrasing differences pass, a different task doesn't.

**Order-independent matching.** Every (expected, actual) pair is scored by task
similarity with a tiebreak when owners agree, then greedily assigned best-first,
each side used once. Array position is never assumed.

**Pass/fail.** A case passes only if the count matches *and* every expected item
has a match with all four fields correct. Unmatched expected items count as fully
wrong; leftover extracted items are reported as invented. Cases are
all-or-nothing — per-field accuracy is where partial credit shows.

**No LLM judges the LLM.** Scoring is string and date comparison: free, instant,
same verdict every time. The runner exits `0` only if every case passes, so it can
gate CI.

## 3. Test coverage

**Dev set (12 cases)** — two clean assignments as a baseline, plus: zero action
items; a suggestion that isn't a commitment; no explicit owner; an ambiguous owner
("someone needs to…"); a missing due date; two tasks in one sentence; one owner
holding several tasks; relative dates ("tomorrow", "by Friday"); a task reassigned
later in the meeting; a filler-heavy transcript with interruptions; urgency that
should set `priority: high`.

**Holdout set (8 cases)**, written after the prompt was frozen: a plain assignment;
urgency with no date (must not become a `due_date`); an idea nobody picked up; work
agreed necessary but unowned; two relative weekdays in one line; a mid-discussion
handoff; a pure status update; one owner with three stacked tasks of mixed
deadline and priority.

**20 cases, 23 expected action items.**

## 4. Results

**Current live result: not verified in this environment** — no `ANTHROPIC_API_KEY`
and extraction dependencies unavailable, so the harness fell back to its mock.
Before submission, run both with the configured API key:

| Set | Cases | Result |
| --- | --- | --- |
| `eval/cases.json` (dev) | 12 | run `python -m eval.run_eval` to fill in |
| `eval/holdout.json` (holdout) | 8 | run `python -m eval.run_eval eval/holdout.json` to fill in |

Two cautions for whoever fills those in:

- **`README.md` records 12/12 and 8/8** (Claude Opus 5, 2026-09-13) from the
  extraction owner's run. That was **not reproduced here** — re-run and confirm it
  before presenting it.
- The dev set was used to tune the prompt, so its score is a training number. The
  holdout set was written after the prompt was frozen — **that's the number that
  says it generalizes.** Report them separately, never merged.

For reference, the built-in mock scores **7/12 (58.3%)** dev and **3/8 (37.5%)**
holdout. Not a product number — evidence the suite discriminates.

## 5. Guardrails

All present in code today:

- **Dry-run by default.** `DRY_RUN` defaults to `true`, read at call time; all three
  connectors check it before any write and log "would create X". The orchestrator
  prints `DRY RUN` or `LIVE` on every run.
- **Structured output + schema validation.** Extraction parses into a Pydantic
  model, so `priority` can only be `high`/`medium`/`low` and a malformed response
  fails at the boundary, not inside a connector.
- **Retries with backoff.** Connector calls make up to 3 attempts (1s → 2s → 4s),
  retrying timeouts, `429`s and `5xx`s. Other statuses raise immediately with the
  response body attached, so the real cause is visible.
- **Zero action items is a real answer.** The prompt requires an empty list over an
  invented task, Slack posts an explicit "no action items found" recap, and four
  eval cases assert it.
- **Per-item, per-connector failure isolation.** Each call is wrapped individually;
  failures are recorded as `{stage, task, error}` and the run continues. Only fully
  succeeded items count as created, and the process exits non-zero if anything
  failed.
- **Extractor provenance in the report.** The harness names the extractor behind a
  score and warns when it's the mock, so a mock run can't pass as a real one.

## 6. Known limitations

- **20 cases is hackathon scale.** One case flipping moves a set by 8.3 points
  (dev) or 12.5 (holdout). Directional, not statistical.
- **Surface-level task matching.** Similarity is character-based, not semantic: a
  correct paraphrase can fail the threshold, and a wrong task reusing the
  transcript's wording can pass.
- **Answer keys encode one reasonable reading.** "Urgent or merely important" is a
  judgement a careful human would sometimes make differently.
- **`due_date` is validated as a string, not a date** — an impossible date would
  satisfy the schema.
- **Untested:** unusual relative dates ("end of next quarter"), long transcripts
  (there's no chunking), non-English and multi-meeting input.
- **The extractor isn't deterministic even though the scorer is.** Run-to-run
  variance is not yet measured.
- **Terminal report only** — no results written to disk, no CI workflow yet, though
  the exit code already suits one. *(Planned.)*

## 7. Reliability philosophy

We're not claiming the agent is perfect — we're claiming we know where it breaks.
We wanted failures to be measurable, reproducible, and visible rather than
demonstrating one successful transcript and assuming the system works generally.
That's why the suite includes the cases most likely to embarrass us, why dev and
holdout are reported separately, why every failure prints its specific reason, and
why a run scoring the mock says so in its first line.
