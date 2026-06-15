"""Critic agent: reviews the draft report and decides approve vs. revise.

The critic asks the LLM to return a small JSON verdict (approved + feedback)
so the graph's routing logic (app.core.graph.route_after_critic) can make a
deterministic decision. If the revision budget is already exhausted, the
critic short-circuits to "approved" regardless of the LLM's opinion, since
the graph will end the loop anyway and we don't want a misleading
"not approved" critique on the final output.
"""

from __future__ import annotations

import json
import logging
import re
import time

from app.agents.common import make_trace_entry, truncate
from app.core.llm_client import call_llm
from app.core.state import WorkflowState
from app.models.schemas import AgentName

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Critic agent in a multi-agent report-generation system.

You are given the original task and a draft report. Evaluate the draft for:
- Completeness (does it cover the task adequately?)
- Accuracy and coherence
- Structure and clarity

Respond with ONLY a JSON object (no markdown fences, no extra text) of the form:
{"approved": true|false, "feedback": "short, specific, actionable feedback"}

If the draft is good enough to ship, set approved to true and feedback can be
brief praise or minor notes. If it needs work, set approved to false and give
specific, actionable feedback on what to improve."""


def _parse_verdict(raw: str) -> tuple[bool, str]:
    """Parse the critic's JSON verdict, with a safe fallback if parsing fails."""
    text = raw.strip()

    # Strip markdown code fences if the model added them despite instructions.
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()

    try:
        data = json.loads(text)
        approved = bool(data.get("approved", False))
        feedback = str(data.get("feedback", "")).strip() or "No feedback provided."
        return approved, feedback
    except (json.JSONDecodeError, AttributeError):
        logger.warning("Critic returned non-JSON verdict, defaulting to approved=False: %r", raw)
        return False, raw.strip() or "Critic response could not be parsed."


def critic_node(state: WorkflowState) -> dict:
    started_at = time.time()
    task = state["task"]
    draft = state.get("draft", "")
    revision_count = state.get("revision_count", 0)
    max_revisions = state.get("max_revisions", 2)

    budget_exhausted = revision_count >= max_revisions

    try:
        raw_verdict = call_llm(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=f"Task: {task}\n\nDraft report:\n{draft}",
            temperature=0.0,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Critic node failed for task %s", state.get("task_id"))
        entry = make_trace_entry(
            agent=AgentName.CRITIC,
            input_summary=truncate(draft),
            output=f"ERROR: {exc}",
            started_at=started_at,
            error=True,
            revision_count=revision_count,
        )
        return {"error": str(exc), "trace": [entry]}

    approved, feedback = _parse_verdict(raw_verdict)

    if budget_exhausted and not approved:
        feedback = (
            f"{feedback}\n\n(Revision budget exhausted after {revision_count} "
            f"revision(s); shipping best-effort draft.)"
        )
        approved = True

    entry = make_trace_entry(
        agent=AgentName.CRITIC,
        input_summary=truncate(draft),
        output=feedback,
        started_at=started_at,
        approved=approved,
        revision_count=revision_count,
        budget_exhausted=budget_exhausted,
    )

    update: dict = {
        "critique": feedback,
        "critique_approved": approved,
        "trace": [entry],
    }

    if not approved:
        update["revision_count"] = revision_count + 1

    return update
