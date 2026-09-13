"""
Comparison, matching, and scoring logic for the reliability eval harness.

This module is intentionally dependency-free and deterministic: no LLM is
used to judge the extractor's output, so results are cheap, repeatable, and
explainable to judges.
"""

from __future__ import annotations

import datetime
import difflib
import re
from dataclasses import dataclass, field
from typing import Optional

TASK_MATCH_THRESHOLD = 0.6

_DATE_FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%B %d %Y", "%b %d, %Y"]


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def normalize_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = value.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def normalize_owner(value: Optional[str]) -> Optional[str]:
    return normalize_text(value)


def normalize_priority(value: Optional[str]) -> Optional[str]:
    return normalize_text(value)


def normalize_date(value: Optional[str]) -> Optional[str]:
    """Best-effort normalization to an ISO 'YYYY-MM-DD' string. Falls back to
    a normalized raw string if the format isn't recognized, so two identical
    unparseable strings still compare equal."""
    if value is None:
        return None
    raw = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return normalize_text(raw)


def task_similarity(a: Optional[str], b: Optional[str]) -> float:
    norm_a, norm_b = normalize_text(a) or "", normalize_text(b) or ""
    if not norm_a and not norm_b:
        return 1.0
    return difflib.SequenceMatcher(None, norm_a, norm_b).ratio()


# ---------------------------------------------------------------------------
# Matching: pair each expected item with the most similar actual item
# ---------------------------------------------------------------------------

@dataclass
class MatchResult:
    expected_index: int
    actual_index: Optional[int]
    similarity: float


def match_items(expected: list[dict], actual: list[dict]) -> list[MatchResult]:
    """Greedy best-match pairing by task-text similarity (with a small owner
    bonus to help break ties). Simple on purpose: sort every possible pair by
    score, then walk the list assigning the best available match to each side
    exactly once."""
    candidates = []
    for e_idx, exp in enumerate(expected):
        for a_idx, act in enumerate(actual):
            score = task_similarity(exp.get("task"), act.get("task"))
            if normalize_owner(exp.get("owner")) == normalize_owner(act.get("owner")):
                score += 0.001
            candidates.append((score, e_idx, a_idx))

    candidates.sort(key=lambda c: c[0], reverse=True)

    matched_expected: dict[int, int] = {}
    used_actual: set[int] = set()
    for score, e_idx, a_idx in candidates:
        if e_idx in matched_expected or a_idx in used_actual:
            continue
        matched_expected[e_idx] = a_idx
        used_actual.add(a_idx)

    results = []
    for e_idx in range(len(expected)):
        a_idx = matched_expected.get(e_idx)
        sim = task_similarity(expected[e_idx].get("task"), actual[a_idx].get("task")) if a_idx is not None else 0.0
        results.append(MatchResult(expected_index=e_idx, actual_index=a_idx, similarity=sim))
    return results


# ---------------------------------------------------------------------------
# Case evaluation
# ---------------------------------------------------------------------------

@dataclass
class FieldTally:
    correct: int = 0
    total: int = 0

    def record(self, is_correct: bool):
        self.total += 1
        if is_correct:
            self.correct += 1


@dataclass
class ItemScore:
    task_ok: bool
    owner_ok: bool
    due_ok: bool
    priority_ok: Optional[bool]  # None if the case's expected item has no priority to check


@dataclass
class CaseResult:
    case_id: str
    description: str
    expected_count: int
    actual_count: int
    count_ok: bool
    task_ok: bool
    owner_ok: bool
    due_ok: bool
    priority_ok: bool
    passed: bool
    reasons: list[str] = field(default_factory=list)
    item_scores: list[ItemScore] = field(default_factory=list)


def evaluate_case(case: dict, actual: list[dict]) -> CaseResult:
    expected = case.get("expected", [])
    matches = match_items(expected, actual)
    used_actual_indices = {m.actual_index for m in matches if m.actual_index is not None}

    reasons: list[str] = []
    task_ok = owner_ok = due_ok = priority_ok = True
    item_scores: list[ItemScore] = []

    for m in matches:
        exp = expected[m.expected_index]
        exp_label = exp.get("task") or "(unnamed task)"

        if m.actual_index is None:
            task_ok = owner_ok = due_ok = priority_ok = False
            reasons.append(f"missing expected item: '{exp_label}' (owner={exp.get('owner')!r})")
            item_scores.append(ItemScore(
                task_ok=False, owner_ok=False, due_ok=False,
                priority_ok=(False if exp.get("priority") is not None else None),
            ))
            continue

        act = actual[m.actual_index]

        item_task_ok = m.similarity >= TASK_MATCH_THRESHOLD
        if not item_task_ok:
            task_ok = False
            reasons.append(
                f"task mismatch for expected '{exp_label}': got '{act.get('task')}' "
                f"(similarity {m.similarity:.2f} < {TASK_MATCH_THRESHOLD})"
            )

        item_owner_ok = normalize_owner(exp.get("owner")) == normalize_owner(act.get("owner"))
        if not item_owner_ok:
            owner_ok = False
            reasons.append(
                f"owner mismatch for '{exp_label}': expected {exp.get('owner')!r}, got {act.get('owner')!r}"
            )

        item_due_ok = normalize_date(exp.get("due_date")) == normalize_date(act.get("due_date"))
        if not item_due_ok:
            due_ok = False
            reasons.append(
                f"due_date mismatch for '{exp_label}': expected {exp.get('due_date')!r}, got {act.get('due_date')!r}"
            )

        exp_priority = exp.get("priority")
        item_priority_ok = None
        if exp_priority is not None:
            item_priority_ok = normalize_priority(exp_priority) == normalize_priority(act.get("priority"))
            if not item_priority_ok:
                priority_ok = False
                reasons.append(
                    f"priority mismatch for '{exp_label}': expected {exp_priority!r}, got {act.get('priority')!r}"
                )

        item_scores.append(ItemScore(
            task_ok=item_task_ok, owner_ok=item_owner_ok, due_ok=item_due_ok, priority_ok=item_priority_ok,
        ))

    extra_actual = [a for i, a in enumerate(actual) if i not in used_actual_indices]
    count_ok = len(expected) == len(actual)
    if not count_ok:
        reasons.append(
            f"expected {len(expected)} item(s), got {len(actual)}"
            + (f" -- unmatched extra item(s): {[a.get('task') for a in extra_actual]}" if extra_actual else "")
        )

    passed = count_ok and task_ok and owner_ok and due_ok and priority_ok

    return CaseResult(
        case_id=case["id"],
        description=case.get("description", ""),
        expected_count=len(expected),
        actual_count=len(actual),
        count_ok=count_ok,
        task_ok=task_ok,
        owner_ok=owner_ok,
        due_ok=due_ok,
        priority_ok=priority_ok,
        passed=passed,
        reasons=reasons,
        item_scores=item_scores,
    )
