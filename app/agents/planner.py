"""Planner agent: breaks the user's task into a structured research/report plan."""

from __future__ import annotations

import logging
import time

from app.agents.common import make_trace_entry, truncate
from app.core.llm_client import call_llm
from app.core.state import WorkflowState
from app.models.schemas import AgentName

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Planner agent in a multi-agent report-generation system.

Given a task description, produce a concise, structured plan for how to research
and write a report on it. The plan should:
- Break the task into 3-6 concrete sub-topics or research questions.
- Suggest a logical section structure for the final report.
- Be written as a short numbered/bulleted outline, not prose.

Do not write the report itself. Only output the plan."""


def planner_node(state: WorkflowState) -> dict:
    started_at = time.time()
    task = state["task"]

    try:
        plan = call_llm(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=f"Task: {task}\n\nProduce a plan as described.",
            temperature=0.3,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Planner node failed for task %s", state.get("task_id"))
        entry = make_trace_entry(
            agent=AgentName.PLANNER,
            input_summary=truncate(task),
            output=f"ERROR: {exc}",
            started_at=started_at,
            error=True,
        )
        return {"error": str(exc), "trace": [entry]}

    entry = make_trace_entry(
        agent=AgentName.PLANNER,
        input_summary=truncate(task),
        output=plan,
        started_at=started_at,
    )

    return {"plan": plan, "trace": [entry]}
