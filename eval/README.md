# Reliability Evaluation Harness

This directory contains the reliability/evaluation layer for the
Meeting-to-Action Agent. It answers one question for judges:

**"How reliably does the extraction step turn a raw transcript into correct
action items?"**

It is deliberately independent of every other integration (Slack, GitHub,
Notion/Sheets, the real LLM). It only tests the extraction step, in
isolation, against a fixed set of known-correct examples.

## What is being evaluated

Given a meeting transcript, the extractor should return a list of action
items shaped like:

```json
{"task": "fix the login bug", "owner": "Sarah", "due_date": "2026-09-18", "priority": "medium"}
```

For each of the 12 test transcripts in `eval/cases.json`, we compare the
extractor's actual output against a hand-written expected answer key and
check:

- **Count** — did it return the right number of action items?
- **Task** — is the task description close enough in meaning (fuzzy match, not exact string equality)?
- **Owner** — does the owner match exactly (including "no owner stated" cases)?
- **Due date** — does the date match after normalizing formats?
- **Priority** — does the priority match, when the expected answer specifies one?

## Why these test cases exist

The 12 cases in `cases.json` were chosen to cover both the easy path and the
adversarial cases that actually break naive extractors:

| Case | What it stresses |
|---|---|
| `clear_two_tasks` | Baseline happy path |
| `no_action_items` | Extractor must not hallucinate tasks from a status update |
| `no_explicit_owner` | Must return `null`, not invent an owner |
| `no_due_date` | Must return `null`, not invent a date |
| `two_tasks_one_sentence` | Two action items packed into one sentence |
| `one_owner_multiple_tasks` | One person assigned multiple separate tasks |
| `relative_dates` | "tomorrow" / "by Friday" resolved against a fixed reference date |
| `suggestion_not_action` | A suggestion ("maybe we could...") must NOT become an action item |
| `corrected_action_item` | An assignment that gets overridden later in the same meeting |
| `messy_transcript` | Filler words, interruptions, cross-talk around a real action item |
| `ambiguous_owner` | "Someone needs to..." with no name — owner must stay `null` |
| `urgent_priority` | Urgency language ("ASAP") should map to `priority: high` |

Each case also carries a `reference_date` (or falls back to the top-level
one in `cases.json`) so relative-date resolution is deterministic and
repeatable across runs.

## How to run it

```bash
python3 eval/run_eval.py
```

This prints a per-case PASS/FAIL table, an overall pass rate, and per-field
accuracy percentages, e.g.:

```
Meeting-to-Action Reliability Evaluation

Case                          Count   Owner  Due Date   Task  Result
--------------------------------------------------------------------
clear_two_tasks                 ✓       ✓        ✓       ✓    PASS
...

Overall: 7/12 passed
Pass rate: 58.3%

Task accuracy: 71%
Owner accuracy: 79%
Due-date accuracy: 79%
Priority accuracy: 86%

Failures:

FAIL: two_tasks_one_sentence
  - missing expected item: 'update the docs' (owner='Sarah')
  ...
```

The exit code is `0` if every case passes and `1` otherwise, so this can be
wired into CI later without extra work.

## What the metrics mean

- **Pass rate** — the fraction of test cases where *every* checked field for
  *every* action item in that case was correct (count included). A case is
  all-or-nothing.
- **Task / Owner / Due-date / Priority accuracy** — computed at the
  individual action-item level across all cases (not per-case), so one case
  with three action items contributes three data points, not one. Priority
  accuracy only counts items where the expected answer specifies a
  priority.

## How matching works

Extractors won't always return items in the same order as the answer key
(and sometimes return a different count entirely). Rather than comparing
`actual[0]` to `expected[0]` blindly, `eval/evaluator.py`:

1. Scores every (expected item, actual item) pair by text similarity of the
   `task` field (`difflib.SequenceMatcher`, after lowercasing/punctuation
   stripping), with a tiny bonus if the owners also match.
2. Greedily assigns the highest-scoring pairs first, until every expected
   item has been matched to at most one actual item (or run out of
   candidates).
3. Any expected item that never gets matched counts as fully wrong (missing
   task/owner/due/priority). Any extra actual item left over is reported as
   an unmatched/hallucinated item.

This keeps matching simple and explainable, at the cost of not being a
formally optimal assignment (see Limitations below).

## Normalization rules

To avoid penalizing harmless formatting differences:

- Text is lowercased, punctuation-stripped, and whitespace-collapsed before
  comparison.
- Task text uses a similarity **threshold** (0.6), not exact match, so
  reasonable paraphrasing still passes — but a genuinely wrong task still
  fails.
- Dates are parsed from a few common formats (`YYYY-MM-DD`, `MM/DD/YYYY`,
  `Month DD, YYYY`) and normalized to ISO before comparison.

No LLM is used anywhere in the scoring path. This keeps the evaluation
deterministic, free to run, and fast enough to run on every change.

## How to connect the real extractor

The evaluator never calls an extraction implementation directly — it goes
through `eval/extractor_adapter.py`, which currently falls back to a small
rule-based mock (see below) because no real extractor exists yet.

**To plug in the real extractor:** create `extraction/extract.py` at the
repo root with:

```python
def extract_actions(transcript: str, reference_date: str | None = None) -> list[dict]:
    # returns [{"task": ..., "owner": ..., "due_date": ..., "priority": ...}, ...]
    ...
```

`eval/extractor_adapter.run_extractor()` will automatically import and use
`extraction.extract.extract_actions` the moment that module exists —
nothing else in the eval harness needs to change. `reference_date` is
passed through so the real extractor can resolve relative dates
("tomorrow", "by Friday") the same way the test cases expect.

## About the mock extractor

Until the real extractor exists, `extractor_adapter.py` uses a small
regex-based stub so the harness itself can be built, run, and demoed
end-to-end. It is intentionally simple and does **not** represent the
quality of the real LLM-based extractor — its current pass rate (see output
above) reflects the mock's limitations, not the project's.

## Known limitations

- **Matching is greedy, not globally optimal.** In rare cases with many
  similar-sounding tasks, greedy assignment could pick a slightly
  suboptimal pairing. Fine for a suite this size; would need a proper
  assignment algorithm (e.g. Hungarian) at larger scale.
- **Task similarity is surface-level.** `difflib` compares character
  sequences, not meaning — a paraphrase that reuses few of the same words
  could score below threshold even if it's semantically correct, and a
  wrong task that happens to share a lot of words could score above it.
- **Case-level pass/fail is all-or-nothing.** A case with two action items
  where only one field on one item is wrong still counts as a full case
  failure, even though the per-field accuracy numbers show it was mostly
  right.
- **Date normalization covers common formats only.** An extractor that
  returns dates in an unlisted format will fail the due-date check even if
  the date is correct; add formats to `_DATE_FORMATS` in `evaluator.py` as
  needed.
- **The mock extractor is a toy.** It's regex/keyword-based and will miss
  or mis-parse things a real LLM would handle fine (and vice versa) — see
  the failures it currently produces for examples of exactly the kind of
  mistakes this harness is designed to catch.

## Files in this directory

- `cases.json` — the test suite (reference date + 12 transcript/answer-key pairs)
- `extractor_adapter.py` — pluggable interface; real-extractor integration point + mock stub
- `evaluator.py` — normalization, matching, and per-case scoring logic
- `run_eval.py` — CLI runner and terminal report
- `README.md` — this file
