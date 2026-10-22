"""Verified reference implementation of a deterministic dependency scheduler.

This example is a benchmark fixture, not an executable Ground Space task queue.
"""
from __future__ import annotations

import heapq
from collections import defaultdict
from typing import Any


def schedule_tasks(tasks: list[dict[str, Any]]) -> list[str]:
    """Return dependency-safe task IDs, highest ready priority first.

    Identical priorities are resolved by ascending task ID. The input is not
    mutated. Duplicate IDs, missing dependencies, cycles and invalid records
    raise ValueError. Complexity: O(V + E + V log V), with V tasks and E
    distinct dependency edges.
    """
    if not isinstance(tasks, list):
        raise ValueError("tasks must be a list")

    by_id: dict[str, dict[str, Any]] = {}
    for task in tasks:
        if not isinstance(task, dict):
            raise ValueError("each task must be a dictionary")
        task_id = task.get("id")
        if not isinstance(task_id, str) or not task_id:
            raise ValueError("task id must be a nonempty string")
        if task_id in by_id:
            raise ValueError(f"duplicate task id: {task_id}")
        by_id[task_id] = task

    outgoing: dict[str, list[str]] = defaultdict(list)
    indegree = {task_id: 0 for task_id in by_id}
    for task_id, task in by_id.items():
        priority = task.get("priority")
        if type(priority) is not int:
            raise ValueError(f"priority for {task_id} must be an integer")
        dependencies = task.get("depends_on")
        if not isinstance(dependencies, list):
            raise ValueError(f"depends_on for {task_id} must be a list")
        seen: set[str] = set()
        for dependency in dependencies:
            if not isinstance(dependency, str) or dependency not in by_id:
                raise ValueError(f"missing or invalid dependency {dependency!r} for {task_id}")
            if dependency not in seen:
                seen.add(dependency)
                outgoing[dependency].append(task_id)
                indegree[task_id] += 1

    ready = [(-by_id[task_id]["priority"], task_id)
             for task_id, degree in indegree.items() if degree == 0]
    heapq.heapify(ready)
    result: list[str] = []
    while ready:
        _, task_id = heapq.heappop(ready)
        result.append(task_id)
        for dependent in outgoing[task_id]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                heapq.heappush(ready, (-by_id[dependent]["priority"], dependent))

    if len(result) != len(by_id):
        raise ValueError("circular dependency detected")
    return result
