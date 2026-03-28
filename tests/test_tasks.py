"""Tests for nexus.tasks (TaskQueue, retry, scheduling)."""

import asyncio
import pytest
from nexus.tasks import TaskQueue, TaskStatus


@pytest.mark.asyncio
async def test_enqueue_and_complete():
    q = TaskQueue(max_workers=2)

    @q.task(retries=0)
    async def add(a, b):
        return a + b

    await q.start()
    task_id = await q.enqueue(add, 3, 4)
    await asyncio.sleep(0.3)
    t = q.get_task(task_id)
    assert t is not None
    assert t.status == TaskStatus.COMPLETED
    assert t.result == 7
    await q.stop()


@pytest.mark.asyncio
async def test_task_retry():
    q = TaskQueue(max_workers=1)
    count = 0

    @q.task(retries=2)
    async def flaky():
        nonlocal count
        count += 1
        if count < 3:
            raise ValueError("not yet")
        return "ok"

    await q.start()
    task_id = await q.enqueue(flaky)
    await asyncio.sleep(5)
    t = q.get_task(task_id)
    assert t.status == TaskStatus.COMPLETED
    assert count == 3
    await q.stop()


@pytest.mark.asyncio
async def test_task_max_retries_fail():
    q = TaskQueue(max_workers=1)

    @q.task(retries=1)
    async def always_fail():
        raise RuntimeError("always fails")

    await q.start()
    task_id = await q.enqueue(always_fail)
    await asyncio.sleep(4)
    t = q.get_task(task_id)
    assert t.status == TaskStatus.FAILED
    await q.stop()


@pytest.mark.asyncio
async def test_get_task_not_found():
    q = TaskQueue()
    assert q.get_task("nonexistent-id") is None


@pytest.mark.asyncio
async def test_list_tasks():
    q = TaskQueue(max_workers=2)

    @q.task(retries=0)
    async def noop():
        return True

    await q.start()
    await q.enqueue(noop)
    await q.enqueue(noop)
    await asyncio.sleep(0.3)
    tasks = q.list_tasks(status=TaskStatus.COMPLETED)
    assert len(tasks) == 2
    await q.stop()
