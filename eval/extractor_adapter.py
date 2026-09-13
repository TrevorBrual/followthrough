"""
Pluggable interface to the meeting action-item extractor.

INTEGRATION POINT FOR THE EXTRACTION TEAMMATE
----------------------------------------------
Create a module at `extraction/extract.py` (relative to the repo root)
exposing a function with this exact signature:

    def extract_actions(transcript: str, reference_date: str | None = None) -> list[dict]:
        \"\"\"Return a list of action items extracted from `transcript`.\"\"\"
        ...

Each returned dict should look like:

    {
        "task": "fix the login bug",
        "owner": "Sarah",       # or None if no owner is stated
        "due_date": "2026-09-18",  # ISO date string, or None if no date is stated
        "priority": "medium",   # "high" | "medium" | "low", or None
    }

`reference_date` is an ISO date string (e.g. "2026-09-13") the eval harness
passes in so relative dates like "tomorrow" or "by Friday" can be resolved
deterministically. It may be None if no reference date is available.

As soon as `extraction/extract.py` exists and defines `extract_actions`,
this adapter will automatically use it instead of the mock below -- no
changes needed anywhere else in the eval harness.

Until then, `run_extractor` falls back to a small rule-based mock so the
evaluation harness itself can be built, run, and demoed end-to-end. The
mock is deliberately simple and imperfect (see limitations in eval/README.md)
-- it is NOT meant to represent real extraction quality.
"""

from __future__ import annotations

import datetime
import importlib
import re
from typing import Optional

EXTRACTOR_MODULE = "extraction.extract"
EXTRACTOR_FUNC = "extract_actions"


def run_extractor(transcript: str, reference_date: Optional[str] = None) -> list[dict]:
    """Single entry point the eval harness calls. Prefers the real extractor
    if one has been plugged in, otherwise falls back to the mock."""
    real = _load_real_extractor()
    if real is not None:
        return real(transcript, reference_date=reference_date)
    return _mock_extract(transcript, reference_date)


def _load_real_extractor():
    try:
        module = importlib.import_module(EXTRACTOR_MODULE)
    except ImportError:
        return None
    return getattr(module, EXTRACTOR_FUNC, None)


# ---------------------------------------------------------------------------
# Mock extractor (stub only -- replace by adding extraction/extract.py)
# ---------------------------------------------------------------------------

_NON_NAME_WORDS = {
    "the", "this", "that", "these", "those", "someone", "something",
    "it", "we", "they", "i", "you", "maybe", "anyway", "okay", "ok",
}

_VERB_PHRASE = r"(?:will|needs to|is going to|has to|should)"

# "<Name> will/needs to/... <task text>"
_OWNED_ACTION_RE = re.compile(
    rf"\b([A-Z][a-zA-Z]+)\s+{_VERB_PHRASE}\s+(.+)"
)

# fallback: verb phrase with no clear name in front, e.g. "the server needs to be restarted"
_UNOWNED_ACTION_RE = re.compile(rf"\b{_VERB_PHRASE}\b\s+(.+)")

_SUGGESTION_MARKERS = ("maybe", "could", "might", "just something to think about")

_HIGH_PRIORITY_WORDS = ("urgent", "asap", "critical", "immediately")
_LOW_PRIORITY_WORDS = ("no rush", "whenever", "low priority")

_DATE_ISO_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _mock_extract(transcript: str, reference_date: Optional[str]) -> list[dict]:
    sentences = re.split(r"(?<=[.?!])\s+", transcript.strip())
    items = []
    for sentence in sentences:
        clean = sentence.strip()
        if not clean:
            continue
        lowered = clean.lower()

        if any(marker in lowered for marker in _SUGGESTION_MARKERS):
            continue

        owner = None
        task_text = None

        m = _OWNED_ACTION_RE.search(clean)
        if m:
            candidate, rest = m.group(1), m.group(2)
            if candidate.lower() not in _NON_NAME_WORDS:
                owner = candidate
            task_text = rest
        else:
            m2 = _UNOWNED_ACTION_RE.search(clean)
            if m2:
                task_text = m2.group(1)

        if task_text is None:
            continue

        due_date = _extract_date(clean, reference_date)
        priority = _extract_priority(lowered)
        task = _clean_task_text(task_text)

        if not task:
            continue

        items.append({
            "task": task,
            "owner": owner,
            "due_date": due_date,
            "priority": priority,
        })

    return items


def _clean_task_text(text: str) -> str:
    text = re.sub(r"\bby\s+(tomorrow|\d{4}-\d{2}-\d{2}|" + "|".join(_WEEKDAYS) + r")\b.*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(asap|urgent(ly)?|immediately|no rush|whenever)\b.*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[,.;]+\s*$", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ,.-")
    return text


def _extract_date(sentence: str, reference_date: Optional[str]) -> Optional[str]:
    iso_match = _DATE_ISO_RE.search(sentence)
    if iso_match:
        return iso_match.group(1)

    if reference_date is None:
        return None

    ref = datetime.date.fromisoformat(reference_date)
    lowered = sentence.lower()

    if "tomorrow" in lowered:
        return (ref + datetime.timedelta(days=1)).isoformat()

    for i, weekday in enumerate(_WEEKDAYS):
        if weekday in lowered:
            delta = (i - ref.weekday()) % 7
            if delta == 0:
                delta = 7
            return (ref + datetime.timedelta(days=delta)).isoformat()

    return None


def _extract_priority(lowered_sentence: str) -> Optional[str]:
    if any(word in lowered_sentence for word in _HIGH_PRIORITY_WORDS):
        return "high"
    if any(word in lowered_sentence for word in _LOW_PRIORITY_WORDS):
        return "low"
    return "medium"
