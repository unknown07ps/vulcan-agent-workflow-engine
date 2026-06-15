"""Builds the LangGraph StateGraph that wires together the four agents.

Graph shape:

    START -> planner -> researcher -> formatter -> critic -> (router)
                                            ^                     |
                                            |---- revise ---------|
                                            |
                                          (approve) -> END

The critic node decides whether the draft is good enough. If not, and the
revision budget (max_revisions) hasn't been exhausted, control loops back to
the researcher (to gather more info) and then formatter again. Otherwise the
graph ends, either with an approved report or the best-effort draft.

Node implementations live in app.agents.* and are imported lazily here to keep
this module focused on wiring/control-flow.
"""

from __future__ import annotations

import logging
from typing import Literal

from langgraph.graph import END, StateGraph

from app.core.state import WorkflowState

logger = logging.getLogger(__name__)


def route_if_error(next_node: str):
    """Build a router that goes to `finalize` if state['error'] is set,
    otherwise continues to `next_node`. Used after planner/researcher/formatter
    so an LLM failure short-circuits the rest of the pipeline."""

    def _router(state: WorkflowState) -> str:
        if state.get("error"):
            return "finalize"
        return next_node

    return _router


def route_after_critic(state: WorkflowState) -> Literal["revise", "end"]:
    """Decide whether to loop back for another revision or finish.

    Ends the loop if:
      - the critic approved the draft, or
      - the revision budget has been exhausted.
    """
    if state.get("error"):
        return "end"

    if state.get("critique_approved"):
        return "end"

    revision_count = state.get("revision_count", 0)
    max_revisions = state.get("max_revisions", 2)

    if revision_count >= max_revisions:
        logger.info(
            "Task %s: revision budget exhausted (%s/%s), ending with best-effort draft.",
            state.get("task_id"),
            revision_count,
            max_revisions,
        )
        return "end"

    return "revise"


def finalize(state: WorkflowState) -> WorkflowState:
    """Terminal node: copy the latest draft into final_report if not already set."""
    if state.get("error"):
        # Returning {} is invalid for LangGraph node updates; echo back the
        # existing error so the graph can complete without writing new state.
        return {"error": state["error"]}

    final_report = state.get("draft")
    return {"final_report": final_report}


def build_graph():
    """Construct and compile the LangGraph StateGraph.

    Imports node implementations lazily so that this module can be inspected
    / the graph can be built even before agent implementations exist (useful
    during incremental development).
    """
    # Lazy imports: agent implementations are added in Stage 3.
    from app.agents.critic import critic_node
    from app.agents.formatter import formatter_node
    from app.agents.planner import planner_node
    from app.agents.researcher import researcher_node

    graph = StateGraph(WorkflowState)

    graph.add_node("planner", planner_node)
    graph.add_node("researcher", researcher_node)
    graph.add_node("formatter", formatter_node)
    graph.add_node("critic", critic_node)
    graph.add_node("finalize", finalize)

    graph.set_entry_point("planner")

    graph.add_conditional_edges(
        "planner",
        route_if_error("researcher"),
        {"researcher": "researcher", "finalize": "finalize"},
    )
    graph.add_conditional_edges(
        "researcher",
        route_if_error("formatter"),
        {"formatter": "formatter", "finalize": "finalize"},
    )
    graph.add_conditional_edges(
        "formatter",
        route_if_error("critic"),
        {"critic": "critic", "finalize": "finalize"},
    )

    graph.add_conditional_edges(
        "critic",
        route_after_critic,
        {
            "revise": "researcher",
            "end": "finalize",
        },
    )

    graph.add_edge("finalize", END)

    return graph.compile()
