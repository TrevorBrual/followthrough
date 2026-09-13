# Reliability & Evaluation Brief

## 1. What we evaluate

The riskiest step is the first one: turning messy spoken language into structured
action items. Each becomes a Notion row, a GitHub issue, and a line in a Slack recap —
so a hallucinated task becomes a real issue in someone's tracker.

Extraction returns `task` (an imperative phrase), `owner`, `due_date` (ISO), and
`priority` (`high`/`medium`/`low`), with `owner` and `due_date` null when the meeting
named neither. `src/extract.py` enforces that shape as a Pydantic model. Nothing in
`eval/` imports a connector, so scoring never touches Notion, GitHub, or Slack.

## 2. Methodology

Four JSON files hold short transcripts with hand-written answer keys and a fixed
`reference_date`, so relative dates resolve deterministically. One scorer runs them
all:

```
python -m eval.run_eval                           # dev           (12 cases)
python -m eval.run_eval eval/holdout.json         # holdout        (8 cases)
python -m eval.run_eval eval/adversarial.json     # blind set 1   (10 cases, now tuned)
python -m eval.run_eval eval/adversarial2.json    # blind set 2   (10 cases)
```

Per case we check the item count; per item, `task`, `owner`, `due_date`, `priority`.
Text is normalized and dates converted to ISO before comparison; task text matches on
character similarity at a **0.6 threshold**. Matching is order-independent, so array
position is never assumed. A case passes only if the count matches *and* every expected
item matches on all four fields; extra items are reported as invented. **No LLM judges
the LLM**, so scoring is deterministic.

## 3. Results

Claude Opus 5, 2026-09-13. Four sets, never merged into one figure:

| Set | Cases | Passed | Pass rate | What it means |
| --- | --- | --- | --- | --- |
| dev | 12 | 12 | **100%** | **Tuned** — the prompt was written against these; a training score |
| holdout | 8 | 8 | **100%** | **Unseen** — written after the prompt froze |
| blind set 1 | 10 | 8 | **80%** | **Superseded** — run against the pre-fix prompt; now tuned |
| **blind set 2** | 10 | 9 | **90%** | **Blind, current** — frozen against the fixed prompt, first run |

Blind set 2 per-field accuracy: task **100%**, owner **90%**, due date **100%**,
priority **100%**. **This is the generalization number to quote** — neither the
extractor nor the prompt had seen these cases.

### Chronology

1. Blind set 1 frozen in git, first run: **8/10 (80%)**.
2. Its two failures diagnosed and the prompt fixed (`830936d`).
3. Post-fix diagnostics on set 1: **9/10, 10/10, 9/10** — but that set is now *tuned*,
   so those are training scores, not blind ones.
4. Blind set 2 written and frozen against the fixed prompt, before any run.
5. Set 2 first run: **9/10 (90%)**. An unplanned second run reproduced 9/10 with the
   same failure; the first run stands as the recorded score.

Both blind sets were committed to git before their first execution, so in each case
the answer keys provably predate the score, and neither number is a best-of-several.

### The current failure

**`adv2_delegation_to_absent_person` — wrong owner on a delegated task.** Marcus says
"I'll ask Jordan to update the firewall rules by 2026-09-18" about a colleague who
isn't in the meeting. Task and date came back right; the owner came back as **Jordan**,
not **Marcus**. The extractor tracked who will eventually do the underlying work rather
than who committed to anything in the room — so in production that issue lands on
someone who never agreed to it and wasn't there. Unfixed.

### Set 1's two failures (both since fixed)

It invented an action item out of "we'll sort out the owner offline", and it dropped
the deadline from a conditional commitment where our key expected `2026-09-16`. Half of
that second failure was our own metric — a correct paraphrase scored 0.47 against the
0.6 threshold — and we reported it rather than move the threshold afterwards. The
prompt fix covered both, but not owner attribution, which is what set 2 then caught.

## 4. Guardrails

- **Dry-run by default.** `DRY_RUN` defaults to `true`, read at call time; all three
  connectors check it before any write and log "would create X" instead.
- **Structured output with schema validation.** Extraction parses into a Pydantic
  model, so `priority` can only be `high`/`medium`/`low` and a malformed response fails
  at the boundary, not inside a connector.
- **Retries with backoff.** Connector calls make up to 3 attempts (1s → 2s → 4s) on
  timeouts, `429`s and `5xx`s; other statuses raise with the response body attached.
- **Per-item, per-connector failure isolation.** Each call is wrapped individually and
  the run continues, so one bad row never costs the rest of the meeting. Only fully
  succeeded items count as created; the run exits non-zero on any failure.

## 5. Known limitations

- **40 cases is hackathon scale** — one case moves a set by 8–12 points.
- **A pass rate is a sample, not a capability.** Repeated runs of set 1 spanned 7–9/10
  before the fix and 9–10/10 after; treat the 90% the same way.
- **A blind set survives one prompt change.** Fixing the delegation bug would burn set
  2, so staying honest means writing new ones.
- **Known open bug:** owner attribution when someone commits to chasing work that
  another person will perform.
- **Task matching is character-based, not semantic,** and the answer keys encode one
  reasonable reading of each transcript.
- **Untested:** long transcripts, unusual relative dates, non-English input.

## 6. Reliability philosophy

We're not claiming the agent is perfect — we're claiming we know where it breaks. Both
blind sets were frozen before they ran, we kept a failure we think our own metric
scored unfairly, and finding two real bugs retired set 1 rather than promoting its next
score. The 90% matters not because it is higher than the 80%, but because it was earned
on cases written after the fix — and it still names a bug we have not fixed.
