# Reliability & Evaluation Brief

## 1. What we evaluate

The riskiest step is the first one: turning messy spoken language into structured
action items. Each item becomes a Notion row, a GitHub issue, and a line in a Slack
recap — so a hallucinated task becomes a real issue in someone's tracker.

The schema is the contract between extraction and every connector (`src/extract.py`,
enforced as a Pydantic model):

| Field | Type | Meaning |
| --- | --- | --- |
| `task` | `str` | Imperative phrase — no owner, deadline, or urgency wording |
| `owner` | `str \| None` | Name as used in the transcript; `null` if unclaimed |
| `due_date` | `str \| None` | ISO `YYYY-MM-DD`; `null` if no deadline was set |
| `priority` | `"high" \| "medium" \| "low"` | Schema-constrained; defaults to `medium` |

Nothing in `eval/` imports a connector, so scoring never touches Notion, GitHub, or
Slack.

## 2. Methodology

Three JSON files hold short transcripts with hand-written answer keys and a fixed
`reference_date`, so relative dates resolve deterministically. They cover what breaks
naive extractors: zero action items, suggestions that aren't commitments, unowned work,
missing deadlines, reassignments, cancellations, conditionals. One scorer runs all
three:

```
python -m eval.run_eval                           # dev            (12 cases)
python -m eval.run_eval eval/holdout.json         # holdout         (8 cases)
python -m eval.run_eval eval/adversarial.json     # adversarial 1  (10 cases, now tuned)
python -m eval.run_eval eval/adversarial2.json    # adversarial 2  (10 cases, still blind)
```

Per case we check the item count; per item, `task`, `owner`, `due_date`, `priority`.
Text is normalized and dates converted to ISO before comparison; task text matches on
character similarity at a **0.6 threshold**. Matching is **order-independent** — pairs
are scored by similarity and greedily assigned, never by array position. A case passes
only if the count matches *and* every expected item matches on all four fields; extra
items are reported as invented. **No LLM judges the LLM**, so scoring is deterministic.

## 3. Results

Claude Opus 5, 2026-09-13. The three sets answer different questions, never merged
into one figure:

| Set | Cases | Passed | Pass rate | What it means |
| --- | --- | --- | --- | --- |
| dev | 12 | 12 | **100%** | **Tuned** — the prompt was written against these; a training score |
| holdout | 8 | 8 | **100%** | **Unseen** — written after the prompt froze; the generalization signal |
| adversarial | 10 | 8 | **80%** | **Blind** — authored independently, frozen, run once against prompt `b68f60f4` |

Blind per-field accuracy: task **92%**, owner **100%**, due date **92%**, priority
**100%**.

**The blind set was frozen before it ran.** `eval/adversarial.json` was committed as
blob `b1eba05b` ahead of execution, against `src/extract.py` blob `b68f60f4` — the
answer keys provably predate the score, and the 80% is a first run, not the best of
several.

**Two caveats on that 80%, both learned afterwards.** It is one draw, not a
measurement — repeated runs on that same prompt scored **7–9/10**, so the borderline
cases sit near the model's decision boundary. And the prompt has since been fixed
(`9e55876c`) against both failures below, so that set is now **tuned, not blind**;
re-running it yields a training score. A second blind set,
`eval/adversarial2.json`, is frozen against the fixed prompt and not yet run.

### The two blind failures

**1. `adv_ownership_disagreement` — invented an item.** Three people argue over who
owns the migration checklist and the chair says they'll "sort out the owner offline."
The extractor got the checklist task right, `owner: null` included, then *also*
emitted "Determine the owner of the migration checklist offline." Expected 1, got 2.
Real over-extraction: process talk became a tracked task, and in production that's a
GitHub issue nobody asked for.

**2. `adv_conditional_task` — dropped a conditional deadline.** For "if legal clears
it by Wednesday, I'll get it countersigned the same day", it returned "Get the vendor
contract countersigned once legal clears it" with `due_date: null`. The **due date is
a genuine disagreement**: it read a conditional task as unscheduled, our key expected
`2026-09-16`. Either reading is defensible; we scored against ours and took the loss.
The **task text failure is partly our metric** — the phrasing means the same as the
key's "countersign the vendor contract", but similarity scored 0.47 against the 0.6
threshold. We report it as a failure rather than move the threshold afterwards.

Neither is a crash or schema violation — both are judgement errors on hard input,
which is what the set was built to find. Both are now fixed in the prompt: task text
strips any attached condition, and arranging work is explicitly not the work.

## 4. Guardrails

- **Dry-run by default.** `DRY_RUN` defaults to `true`, read at call time; all three
  connectors check it before any write and log "would create X" instead. Nothing
  irreversible happens until someone flips it.
- **Structured output with schema validation.** Extraction parses into a Pydantic
  model, so `priority` can only be `high`/`medium`/`low` and a malformed response
  fails at the boundary, not inside a connector.
- **Retries with backoff.** Connector calls make up to 3 attempts (1s → 2s → 4s) on
  timeouts, `429`s and `5xx`s; other statuses raise immediately with the response body
  attached.
- **Per-item, per-connector failure isolation.** Each call is wrapped individually and
  the run continues, so one bad row never costs the rest of the meeting. Only fully
  succeeded items count as created; the run exits non-zero on any failure.

## 5. Known limitations

- **30 cases is hackathon scale** — one case flipping moves a set by 8-12 points.
  Directional, not statistical.
- **Two perfect scores are not evidence of perfection.** Dev 100% is a training
  number by construction; 8 holdout cases is a thin basis for a generalization
  claim. The blind 80% is the figure we'd defend.
- **Task matching is surface-level, and answer keys encode one reasonable reading.**
  Both cost us in blind failure 2 — a defensible paraphrase scored as wrong, and a
  conditional deadline our key called differently than the extractor did.
- **Untested:** long transcripts (no chunking), unusual relative dates, non-English
  and multi-meeting input.
- **The extractor isn't deterministic even though the scorer is.** Repeated runs of
  the blind set spanned 7–9/10 before the fix and 9–10/10 after, so any single pass
  rate is a sample, not a capability — ours included.
- **A blind set survives one prompt change.** Tune against its failures and it
  becomes a second dev set, so staying honest means writing new ones.

## 6. Reliability philosophy

We're not claiming the agent is perfect — we're claiming we know where it breaks. We
wanted failures measurable, reproducible, and visible rather than demonstrating one
successful transcript and assuming the system works generally. That's why the hardest
set was frozen in git before it ran, why its 80% sits beside the two 100%s instead of
behind them, why we kept a failure we think our own metric scored unfairly, and why
finding two real bugs retired that set rather than promoting its next score.
