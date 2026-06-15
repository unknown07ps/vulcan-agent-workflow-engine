"""Redis-backed storage for TaskRecord state.

Each task is stored as a single JSON blob under key `task:{task_id}`.
This keeps reads/writes atomic and simple - the workflow isn't high enough
throughput to need finer-grained hash fields, and storing the whole record
as JSON makes it trivial to (de)serialize via the Pydantic model.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Optional

import redis

from app.config import settings
from app.models.schemas import TaskRecord, TaskStatus

logger = logging.getLogger(__name__)

TASK_KEY_PREFIX = "task:"
TASK_INDEX_KEY = "tasks:index"  # sorted set of task_ids by created_at, for listing
DEFAULT_TASK_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days


@lru_cache(maxsize=1)
def get_redis_client() -> redis.Redis:
    """Return a cached Redis client (decode_responses=True for str in/out)."""
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def _key(task_id: str) -> str:
    return f"{TASK_KEY_PREFIX}{task_id}"


class TaskStore:
    """CRUD operations for TaskRecord objects backed by Redis."""

    def __init__(self, client: Optional[redis.Redis] = None, ttl_seconds: int = DEFAULT_TASK_TTL_SECONDS):
        self.client = client or get_redis_client()
        self.ttl_seconds = ttl_seconds

    def save(self, record: TaskRecord) -> None:
        """Persist (create or overwrite) a task record."""
        record.touch()
        payload = record.model_dump_json()
        key = _key(record.task_id)

        pipe = self.client.pipeline()
        pipe.set(key, payload, ex=self.ttl_seconds)
        pipe.zadd(TASK_INDEX_KEY, {record.task_id: record.created_at})
        pipe.execute()

    def get(self, task_id: str) -> Optional[TaskRecord]:
        """Fetch a task record by id, or None if it doesn't exist / expired."""
        raw = self.client.get(_key(task_id))
        if raw is None:
            return None
        return TaskRecord.model_validate_json(raw)

    def exists(self, task_id: str) -> bool:
        return self.client.exists(_key(task_id)) == 1

    def list_recent(self, limit: int = 50) -> list[TaskRecord]:
        """Return the most recently created tasks (that haven't expired)."""
        task_ids = self.client.zrevrange(TASK_INDEX_KEY, 0, limit - 1)
        records: list[TaskRecord] = []
        for task_id in task_ids:
            record = self.get(task_id)
            if record is not None:
                records.append(record)
            else:
                # Record expired from the main hash but lingers in the index; clean up.
                self.client.zrem(TASK_INDEX_KEY, task_id)
        return records

    def delete(self, task_id: str) -> bool:
        pipe = self.client.pipeline()
        pipe.delete(_key(task_id))
        pipe.zrem(TASK_INDEX_KEY, task_id)
        results = pipe.execute()
        return bool(results[0])

    def mark_failed(self, task_id: str, error: str) -> Optional[TaskRecord]:
        record = self.get(task_id)
        if record is None:
            return None
        record.status = TaskStatus.FAILED
        record.error = error
        self.save(record)
        return record


def healthcheck() -> bool:
    """Return True if Redis is reachable."""
    try:
        return get_redis_client().ping()
    except redis.RedisError as exc:
        logger.warning("Redis healthcheck failed: %s", exc)
        return False
