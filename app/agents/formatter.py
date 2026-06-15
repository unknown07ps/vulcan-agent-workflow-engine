"""Formatter agent: turns plan + research into a polished, well-structured report."""

from __future__ import annotations

import logging
import time

from app.agents.common import make_trace_entry, truncate
from app.core.llm_client import call_llm
from app.core.state import WorkflowState
from app.models.schemas import AgentName

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Formatter agent in a multi-agent report-generation system.

You are given a task, a plan, and research findings. Produce a polished,
well-structured final report in Markdown:
- Use a clear title and section headings matching the plan.
- Write in clear, professional prose - synthesize the research, don't just
  copy-paste it verbatim.
- Include a brief executive summary/introduction and a conclusion.
- Keep it well-organized and readable.

Output only the report in Markdown, with no preamble or meta-commentary."""


def formatter_node(state: WorkflowState) -> dict:
    started_at = time.time()
    task = state["task"]
    plan = state.get("plan", "")
    research = state.get("research", "")
    revision_count = state.get("revision_count", 0)
    critique = state.get("critique")

    try:
        user_prompt = f"Task: {task}\n\nPlan:\n{plan}\n\nResearch:\n{research}"
        if critique and revision_count > 0:
            user_prompt += (
                f"\n\nNote: this is revision {revision_count}. The critic previously "
                f"gave this feedback, make sure the report addresses it:\n{critique}"
            )
        user_prompt += "\n\nProduce the final formatted report."

        draft = call_llm(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.4,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Formatter node failed for task %s", state.get("task_id"))
        entry = make_trace_entry(
            agent=AgentName.FORMATTER,
            input_summary=truncate(research),
            output=f"ERROR: {exc}",
            started_at=started_at,
            error=True,
            revision_count=revision_count,
        )
        return {"error": str(exc), "trace": [entry]}

    entry = make_trace_entry(
        agent=AgentName.FORMATTER,
        input_summary=truncate(research),
        output=draft,
        started_at=started_at,
        revision_count=revision_count,
    )

    return {"draft": draft, "trace": [entry]}
