"""Meeting transcript -> structured action items.

Owner: Integrator A. Everything downstream (Notion rows, GitHub issues, the
Slack recap) consumes the shape defined here, so the schema is the contract.
"""

import json
import os
import sys
from datetime import date
from typing import Literal, Optional

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

MODEL = os.getenv("MODEL", "claude-opus-5")

Priority = Literal["high", "medium", "low"]

UNASSIGNED = "Unassigned"


class ActionItem(BaseModel):
    task: str = Field(description="The action to be taken, as an imperative phrase.")
    owner: str = Field(
        description=f"Who committed to the task. '{UNASSIGNED}' if no one clearly owns it."
    )
    due_date: Optional[str] = Field(
        description="ISO date (YYYY-MM-DD), or null if the meeting set no deadline."
    )
    priority: Priority = Field(description="high, medium, or low.")


class Extraction(BaseModel):
    action_items: list[ActionItem]


SYSTEM_PROMPT = f"""\
You extract action items from meeting transcripts.

An action item is a concrete task someone committed to doing after the meeting.

Rules:
- Extract ONLY tasks that are actually committed to in the transcript. If the
  meeting contains no action items, return an empty list. Never invent a task
  to fill the list.
- Discussion, opinions, status updates, and decisions without follow-up work
  are NOT action items.
- If one sentence contains two distinct commitments, emit two separate items.
- owner: the person who took the task on. If ownership is genuinely ambiguous
  or nobody claimed it, use "{UNASSIGNED}" rather than guessing.
- due_date: resolve relative dates ("next Friday", "end of the month") against
  the meeting date given in the user message, and return ISO YYYY-MM-DD. If no
  deadline was stated, return null. Do not invent deadlines.
- priority: "high" when the transcript signals urgency or a blocker, "low" for
  explicitly optional or nice-to-have work, otherwise "medium".
"""


def extract(transcript: str, meeting_date: Optional[str] = None) -> list[dict]:
    """Return action items as a list of {task, owner, due_date, priority} dicts."""
    client = anthropic.Anthropic()
    meeting_date = meeting_date or date.today().isoformat()

    response = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Meeting date: {meeting_date}\n\nTranscript:\n{transcript}",
            }
        ],
        output_format=Extraction,
    )

    return [item.model_dump() for item in response.parsed_output.action_items]


SAMPLE_TRANSCRIPT = """\
Priya: Okay, quick sync on the launch. The signup page is still throwing a 500
on mobile Safari — that's blocking us.
Marcus: I'll take that one. I should have a fix up by Thursday.
Priya: Great. We also still need the pricing copy reviewed before we ship.
Dana: I can do the pricing review, but realistically not until next Monday.
Priya: Works. And someone should eventually clean up the old staging bucket —
not urgent, whenever there's time.
Marcus: Noted. Oh, and I'll also update the changelog once the fix lands.
Priya: Perfect. I think that's everything.
"""


if __name__ == "__main__":
    transcript = sys.stdin.read() if not sys.stdin.isatty() else SAMPLE_TRANSCRIPT
    print(json.dumps(extract(transcript), indent=2))
