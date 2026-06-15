"""Researcher agent: gathers/synthesizes information based on the plan.

On revision passes (when the critic requested changes), it focuses on
addressing the critique while building on prior research rather than
starting from scratch.
"""

from __future__ import annotations

import logging
import time

from app.agents.common import make_trace_entry, truncate
from app.core.llm_client import call_llm
from app.core.state import WorkflowState
from app.models.schemas import AgentName

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_INITIAL = """You are the Researcher agent in a multi-agent report-generation system.

You are given a task and a plan produced by the Planner agent. Your job is to
produce well-organized findings/content for each part of the plan, based on
your own knowledge. Write substantive, factual, informative content - this
will be used directly as source material for the final report.

Use clear section headers matching the plan's structure. Do not write a full
polished report - focus on gathering and organizing information."""

SYSTEM_PROMPT_REVISION = """You are the Researcher agent in a multi-agent report-generation system.

You previously produced research findings, but the Critic agent has requested
changes. You are given the task, the plan, your previous research, and the
critic's feedback. Revise and expand the research to address the feedback -
add missing detail, depth, or sections as requested. Keep what was already
good, but ensure the critic's concerns are addressed.

Output the full revised research (not just a diff)."""


def researcher_node(state: WorkflowState) -> dict:
    started_at = time.time()
    task = state["task"]
    plan = state.get("plan", "")
    critique = state.get("critique")
    prior_research = state.get("research", "")
    revision_count = state.get("revision_count", 0)

    try:
        if critique and prior_research:
            user_prompt = (
                f"Task: {task}\n\n"
                f"Plan:\n{plan}\n\n"
                f"Previous research:\n{prior_research}\n\n"
                f"Critic feedback to address:\n{critique}\n\n"
                f"Produce the revised research."
            )
            research = call_llm(
                system_prompt=SYSTEM_PROMPT_REVISION,
                user_prompt=user_prompt,
                temperature=0.3,
            )
            input_summary = f"[revision {revision_count}] critique: {truncate(critique, 200)}"
        else:
            user_prompt = f"Task: {task}\n\nPlan:\n{plan}\n\nProduce research findings."
            research = call_llm(
                system_prompt=SYSTEM_PROMPT_INITIAL,
                user_prompt=user_prompt,
                temperature=0.3,
            )
            input_summary = truncate(plan)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Researcher node failed for task %s", state.get("task_id"))
        entry = make_trace_entry(
            agent=AgentName.RESEARCHER,
            input_summary=truncate(plan),
            output=f"ERROR: {exc}",
            started_at=started_at,
            error=True,
            revision_count=revision_count,
        )
        return {"error": str(exc), "trace": [entry]}

    entry = make_trace_entry(
        agent=AgentName.RESEARCHER,
        input_summary=input_summary,
        output=research,
        started_at=started_at,
        revision_count=revision_count,
    )

    return {"research": research, "trace": [entry]}
