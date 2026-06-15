"""Runs the agent workflow graph for a task and persists progress to Redis.

The graph itself is stateless (operates on an in-memory WorkflowState dict).
This module bridges that to persisted TaskRecord objects: it loads/creates a
record, streams the graph execution, and writes incremental updates back to
Redis after each node so that polling clients (via the API) see live
progress and traces even while the workflow is still running.
"""

from __future__ import annotations

import logging

from app.core.graph import build_graph
from app.core.state import initial_state
from app.core.store import TaskStore
from app.models.schemas import TaskRecord, TaskStatus

logger = logging.getLogger(__name__)

# Compile the graph once; StateGraph.compile() returns a reusable, stateless
# CompiledGraph that can be invoked/streamed concurrently for different inputs.
_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def _apply_state_to_record(record: TaskRecord, state: dict) -> None:
    """Copy relevant fields from a WorkflowState update/snapshot onto the record."""
    if "plan" in state and state["plan"] is not None:
        record.plan = state["plan"]
    if "research" in state and state["research"] is not None:
        record.research = state["research"]
    if "critique" in state and state["critique"] is not None:
        record.critique = state["critique"]
    if "final_report" in state and state["final_report"] is not None:
        record.final_report = state["final_report"]
    if "revision_count" in state:
        record.revision_count = state["revision_count"]
    if "trace" in state and state["trace"]:
        record.trace.extend(state["trace"])
    if "error" in state and state["error"]:
        record.error = state["error"]


def run_workflow(task_id: str, task: str, max_revisions: int, store: TaskStore | None = None) -> TaskRecord:
    """Execute the full workflow synchronously, persisting progress to Redis.

    Intended to be called from a background task (e.g. FastAPI BackgroundTasks
    or a worker process) since it runs the graph to completion, which may
    involve multiple LLM calls and take significant time.
    """
    store = store or TaskStore()

    record = store.get(task_id)
    if record is None:
        record = TaskRecord(task_id=task_id, task=task, max_revisions=max_revisions)

    record.status = TaskStatus.RUNNING
    store.save(record)

    graph = _get_graph()
    state = initial_state(task_id, task, max_revisions=max_revisions)

    try:
        for step_output in graph.stream(state, stream_mode="updates"):
            # step_output is a dict like {"<node_name>": <partial state update>}
            for node_name, update in step_output.items():
                logger.debug("Task %s: node %s produced update with keys %s", task_id, node_name, list(update.keys()))
                _apply_state_to_record(record, update)
                store.save(record)

        if record.error:
            record.status = TaskStatus.FAILED
        else:
            record.status = TaskStatus.COMPLETED

        store.save(record)
        return record

    except Exception as exc:  # noqa: BLE001
        logger.exception("Workflow run failed for task %s", task_id)
        record.status = TaskStatus.FAILED
        record.error = str(exc)
        store.save(record)
        return record
