"""Deterministic ordering and change impact for component graphs."""

from __future__ import annotations

import bisect
from typing import Literal

from .spec import SolutionSpec, SpecError


def _edges(spec: SolutionSpec) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    dependencies = {component.id: set(component.depends_on) for component in spec.components}
    consumers = {component.id: set() for component in spec.components}
    for component in spec.components:
        for dependency in component.depends_on:
            if dependency not in consumers:
                raise SpecError(f"{component.id} has unknown dependency: {dependency}")
            consumers[dependency].add(component.id)
    return dependencies, consumers


def build_order(spec: SolutionSpec) -> tuple[str, ...]:
    """Return component IDs with dependencies before their consumers."""
    dependencies, consumers = _edges(spec)
    indegree = {component_id: len(edges) for component_id, edges in dependencies.items()}
    ready = sorted(component_id for component_id, count in indegree.items() if count == 0)
    order = []
    while ready:
        component_id = ready.pop(0)
        order.append(component_id)
        for consumer in sorted(consumers[component_id]):
            indegree[consumer] -= 1
            if indegree[consumer] == 0:
                bisect.insort(ready, consumer)
    if len(order) != len(dependencies):
        raise SpecError("dependency cycle in component graph")
    return tuple(order)


def change_impact(
    spec: SolutionSpec,
    component_id: str,
    direction: Literal["consumers", "dependencies", "both"],
) -> tuple[str, ...]:
    """Return the transitive change set in dependency build order."""
    dependencies, consumers = _edges(spec)
    if component_id not in dependencies:
        raise SpecError(f"unknown component: {component_id}")
    if direction not in {"consumers", "dependencies", "both"}:
        raise SpecError(f"unknown direction: {direction}")
    affected = {component_id}
    pending = [component_id]
    while pending:
        current = pending.pop()
        neighbors = set()
        if direction in {"dependencies", "both"}:
            neighbors.update(dependencies[current])
        if direction in {"consumers", "both"}:
            neighbors.update(consumers[current])
        for neighbor in neighbors - affected:
            affected.add(neighbor)
            pending.append(neighbor)
    return tuple(component for component in build_order(spec) if component in affected)
