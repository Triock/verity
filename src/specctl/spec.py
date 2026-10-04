"""Load and validate versioned solution specifications."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class SpecError(ValueError):
    """A solution specification is malformed or inconsistent."""


@dataclass(frozen=True)
class RecoveryPolicy:
    rpo_minutes: int
    rto_minutes: int


@dataclass(frozen=True)
class Component:
    id: str
    kind: str
    language: str
    depends_on: tuple[str, ...]
    data_sets: tuple[str, ...]


@dataclass(frozen=True)
class DataSet:
    id: str
    owner: str
    recovery: RecoveryPolicy


@dataclass(frozen=True)
class SolutionSpec:
    version: int
    id: str
    components: tuple[Component, ...]
    data_sets: tuple[DataSet, ...]


def _object(value: object, location: str) -> dict:
    if not isinstance(value, dict):
        raise SpecError(f"{location} must be an object")
    return value


def _string(value: object, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SpecError(f"{location} must be a nonempty string")
    return value


def _names(value: object, location: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise SpecError(f"{location} must be a list")
    names = tuple(_string(item, location) for item in value)
    if len(names) != len(set(names)):
        raise SpecError(f"{location} contains duplicates")
    return names


def _entries(value: object, location: str) -> list:
    if not isinstance(value, list):
        raise SpecError(f"{location} must be a list")
    return value


def _minutes(value: object, location: str) -> int:
    if type(value) is not int or value < 0:
        raise SpecError(f"{location} must be a nonnegative integer")
    return value


def decode_json(content: bytes | str, location: str) -> object:
    """Decode JSON without silently replacing duplicate object keys."""

    def unique_pairs(pairs: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise SpecError(f"{location}: duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        return json.loads(content, object_pairs_hook=unique_pairs)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SpecError(f"{location}: {exc}") from exc


def parse_spec(raw: dict) -> SolutionSpec:
    root = _object(raw, "spec")
    if root.get("version") != 1 or type(root.get("version")) is not int:
        raise SpecError("version must be 1")
    solution_id = _string(root.get("id"), "id")

    components = []
    seen_components = set()
    for index, entry in enumerate(_entries(root.get("components"), "components")):
        item = _object(entry, f"components[{index}]")
        component_id = _string(item.get("id"), f"components[{index}].id")
        if component_id in seen_components:
            raise SpecError(f"duplicate component: {component_id}")
        seen_components.add(component_id)
        kind = _string(item.get("kind"), f"{component_id}.kind")
        if kind not in {"application", "service", "library", "infrastructure"}:
            raise SpecError(f"{component_id}.kind is unsupported: {kind}")
        components.append(
            Component(
                id=component_id,
                kind=kind,
                language=_string(item.get("language"), f"{component_id}.language"),
                depends_on=_names(item.get("depends_on"), f"{component_id}.depends_on"),
                data_sets=_names(item.get("data_sets"), f"{component_id}.data_sets"),
            )
        )

    data_sets = []
    seen_data_sets = set()
    for index, entry in enumerate(_entries(root.get("data_sets"), "data_sets")):
        item = _object(entry, f"data_sets[{index}]")
        data_id = _string(item.get("id"), f"data_sets[{index}].id")
        if data_id in seen_data_sets:
            raise SpecError(f"duplicate data set: {data_id}")
        seen_data_sets.add(data_id)
        recovery = _object(item.get("recovery"), f"{data_id}.recovery")
        data_sets.append(
            DataSet(
                id=data_id,
                owner=_string(item.get("owner"), f"{data_id}.owner"),
                recovery=RecoveryPolicy(
                    rpo_minutes=_minutes(recovery.get("rpo_minutes"), f"{data_id}.rpo_minutes"),
                    rto_minutes=_minutes(recovery.get("rto_minutes"), f"{data_id}.rto_minutes"),
                ),
            )
        )

    component_ids = {component.id for component in components}
    data_ids = {data.id for data in data_sets}
    for component in components:
        for dependency in component.depends_on:
            if dependency not in component_ids:
                raise SpecError(f"{component.id} has unknown dependency: {dependency}")
        for data_id in component.data_sets:
            if data_id not in data_ids:
                raise SpecError(f"{component.id} has unknown data set: {data_id}")
    for data in data_sets:
        if data.owner not in component_ids:
            raise SpecError(f"{data.id} has unknown owner: {data.owner}")

    dependencies = {component.id: component.depends_on for component in components}
    indegree = {component_id: len(edges) for component_id, edges in dependencies.items()}
    consumers = {component_id: [] for component_id in dependencies}
    for component_id, edges in dependencies.items():
        for dependency in edges:
            consumers[dependency].append(component_id)
    ready = [component_id for component_id, count in indegree.items() if count == 0]
    visited_count = 0
    while ready:
        component_id = ready.pop()
        visited_count += 1
        for consumer in consumers[component_id]:
            indegree[consumer] -= 1
            if indegree[consumer] == 0:
                ready.append(consumer)
    if visited_count != len(dependencies):
        raise SpecError("dependency cycle in component graph")

    return SolutionSpec(1, solution_id, tuple(components), tuple(data_sets))


def load_spec(path: str | Path) -> SolutionSpec:
    source = Path(path)
    try:
        content = source.read_bytes()
    except OSError as exc:
        raise SpecError(f"{source}: {exc}") from exc
    raw = decode_json(content, str(source))
    try:
        return parse_spec(raw)
    except SpecError as exc:
        raise SpecError(f"{source}: {exc}") from exc
