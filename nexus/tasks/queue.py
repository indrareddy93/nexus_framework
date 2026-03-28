"""Async task queue with retry, backoff, and scheduled tasks."""

from __future__ import annotations

import asyncio
import enum
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger("nexus.tasks")


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class TaskRecord:
    """Internal record of a single queued task execution."""

    id: str
    name: str
    fn: Callable
    args: tuple
    kwargs: dict
    max_retries: int
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: str | None = None
    attempts: int = 0
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None


class TaskQueue:
    """
    Async background task queue with configurable workers and automatic retry.

    Usage::

        queue = TaskQueue(max_workers=5)

        @queue.task(retries=3)
        async def send_email(to: str, body: str):
            await smtp.send(to, body)

        await queue.start()
        task_id = await queue.enqueue(send_email, to="user@example.com", body="Hi!")
        task = queue.get_task(task_id)
        await queue.stop()
    """

    def __init__(self, max_workers: int = 4) -> None:
        self.max_workers = max_workers
        self._queue: asyncio.Queue = asyncio.Queue()
        self._tasks: dict[str, TaskRecord] = {}
        self._workers: list[asyncio.Task] = []
        self._running = False
        self._registered: dict[str, int] = {}  # fn name → max_retries

    # ── Decorator ────────────────────────────────────────────────────────────

    def task(self, retries: int = 0) -> Callable:
        """Register a function as a task with automatic retry."""

        def decorator(fn: Callable) -> Callable:
            self._registered[fn.__name__] = retries
            return fn

        return decorator

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start worker coroutines."""
        self._running = True
        for _ in range(self.max_workers):
            worker = asyncio.ensure_future(self._worker())
            self._workers.append(worker)
        logger.debug("TaskQueue started with %d workers", self.max_workers)

    async def stop(self) -> None:
        """Gracefully stop all workers."""
        self._running = False
        for _ in self._workers:
            await self._queue.put(None)  # sentinel
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.debug("TaskQueue stopped")

    # ── Enqueueing ────────────────────────────────────────────────────────────

    async def enqueue(self, fn: Callable, *args: Any, **kwargs: Any) -> str:
        """Enqueue a task and return its ID."""
        max_retries = self._registered.get(fn.__name__, 0)
        record = TaskRecord(
            id=str(uuid.uuid4()),
            name=fn.__name__,
            fn=fn,
            args=args,
            kwargs=kwargs,
            max_retries=max_retries,
        )
        self._tasks[record.id] = record
        await self._queue.put(record)
        return record.id

    async def enqueue_in(self, delay: float, fn: Callable, *args: Any, **kwargs: Any) -> str:
        """Schedule a task to run after *delay* seconds."""
        task_id = str(uuid.uuid4())

        async def _delayed() -> None:
            await asyncio.sleep(delay)
            await self.enqueue(fn, *args, **kwargs)

        asyncio.ensure_future(_delayed())
        return task_id

    # ── Status ────────────────────────────────────────────────────────────────

    def get_task(self, task_id: str) -> TaskRecord | None:
        return self._tasks.get(task_id)

    def list_tasks(self, status: TaskStatus | None = None) -> list[TaskRecord]:
        if status is None:
            return list(self._tasks.values())
        return [t for t in self._tasks.values() if t.status == status]

    # ── Worker ────────────────────────────────────────────────────────────────

    async def _worker(self) -> None:
        while self._running:
            record = await self._queue.get()
            if record is None:
                break  # sentinel
            await self._run_task(record)
            self._queue.task_done()

    async def _run_task(self, record: TaskRecord) -> None:
        record.status = TaskStatus.RUNNING
        record.started_at = time.time()
        record.attempts += 1

        try:
            if asyncio.iscoroutinefunction(record.fn):
                result = await record.fn(*record.args, **record.kwargs)
            else:
                result = record.fn(*record.args, **record.kwargs)
            record.result = result
            record.status = TaskStatus.COMPLETED
            record.completed_at = time.time()
            logger.debug("Task %s [%s] completed", record.name, record.id[:8])
        except Exception as exc:
            record.error = str(exc)
            if record.attempts <= record.max_retries:
                record.status = TaskStatus.RETRYING
                backoff = 2 ** (record.attempts - 1)
                logger.warning(
                    "Task %s failed (attempt %d/%d), retrying in %ds: %s",
                    record.name,
                    record.attempts,
                    record.max_retries + 1,
                    backoff,
                    exc,
                )
                await asyncio.sleep(backoff)
                await self._queue.put(record)
            else:
                record.status = TaskStatus.FAILED
                record.completed_at = time.time()
                logger.error(
                    "Task %s [%s] failed after %d attempts: %s",
                    record.name,
                    record.id[:8],
                    record.attempts,
                    exc,
                )
