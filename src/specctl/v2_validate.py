"""Validate links and declarations across the six v2 specification layers."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass

from .spec import SolutionSpec, SpecError, parse_spec
from .v2_source import V2Sources


@dataclass(frozen=True)
class ValidatedV2:
    resolved: dict
    graph: SolutionSpec
    bootstrap_components: tuple[str, ...]


def _shape(value: object, keys: set[str], where: str) -> dict:
    if not isinstance(value, dict):
        raise SpecError(f"{where} must be an object")
    missing, extra = keys - value.keys(), value.keys() - keys
    if missing or extra:
        raise SpecError(f"{where}: missing {sorted(missing)}, unknown {sorted(extra)}")
    return value


def _text(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SpecError(f"{where} must be a nonempty string")
    return value


def _integer(value: object, where: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise SpecError(f"{where} must be an integer >= {minimum}")
    return value


def _list(value: object, where: str) -> list:
    if not isinstance(value, list):
        raise SpecError(f"{where} must be a list")
    return value


def _names(value: object, where: str, nonempty: bool = False) -> list[str]:
    names = [_text(v, where) for v in _list(value, where)]
    if len(names) != len(set(names)):
        raise SpecError(f"{where} contains duplicates")
    if nonempty and not names:
        raise SpecError(f"{where} must not be empty")
    return sorted(names)


def _collection(layer: dict, layer_name: str, field: str, keys: set[str], id_field: str = "id") -> list[dict]:
    entries = _list(layer[field], f"{layer_name}.{field}")
    seen = set()
    for index, value in enumerate(entries):
        where = f"{layer_name}.{field}[{index}]"
        _shape(value, keys, where)
        ident = _text(value[id_field], f"{where}.{id_field}")
        if ident in seen:
            raise SpecError(f"{where}: duplicate {id_field}: {ident}")
        seen.add(ident)
    return entries


def _reference(value: str, allowed: set[str], where: str) -> None:
    if value not in allowed:
        raise SpecError(f"{where}: unknown reference {value}")


def _digest(value: object, where: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise SpecError(f"{where} must be a SHA-256 digest")
    return value.lower()


def validate_v2(sources: V2Sources) -> ValidatedV2:
    layers = copy.deepcopy(sources.layers)
    if set(layers) != {"product", "behavior", "system", "data", "blueprints", "verification"}:
        raise SpecError("v2 requires all six layers")
    product = _shape(layers["product"], {"version", "actors", "use_cases"}, "product")
    behavior = _shape(layers["behavior"], {"version", "requirements", "contracts"}, "behavior")
    system = _shape(layers["system"], {"version", "components"}, "system")
    data = _shape(layers["data"], {"version", "data_sets"}, "data")
    blueprints = _shape(layers["blueprints"], {"version", "components"}, "blueprints")
    verification = _shape(layers["verification"], {"version", "cases"}, "verification")
    for name, layer in layers.items():
        if type(layer["version"]) is not int or layer["version"] != 1:
            raise SpecError(f"{name}.version must be 1")

    actors = _collection(product, "product", "actors", {"id", "name"})
    actor_ids = {r["id"] for r in actors}
    for r in actors:
        _text(r["name"], f"product.actor {r['id']}.name")
    use_cases = _collection(product, "product", "use_cases", {"id", "actor_id", "goal"})
    use_case_ids = {r["id"] for r in use_cases}
    for r in use_cases:
        _reference(_text(r["actor_id"], f"product.use_case {r['id']}.actor_id"), actor_ids, f"product.use_case {r['id']}.actor_id")
        _text(r["goal"], f"product.use_case {r['id']}.goal")

    contracts = _collection(behavior, "behavior", "contracts", {"id", "revision", "description"})
    contract_by_id = {r["id"]: r for r in contracts}
    for r in contracts:
        _text(r["revision"], f"behavior.contract {r['id']}.revision")
        _text(r["description"], f"behavior.contract {r['id']}.description")
    requirements = _collection(behavior, "behavior", "requirements", {"id", "use_case_id", "statement", "contract_ids"})
    requirement_ids = {r["id"] for r in requirements}
    for r in requirements:
        where = f"behavior.requirement {r['id']}"
        _reference(_text(r["use_case_id"], f"{where}.use_case_id"), use_case_ids, where)
        _text(r["statement"], f"{where}.statement")
        r["contract_ids"] = _names(r["contract_ids"], f"{where}.contract_ids")
        for contract in r["contract_ids"]:
            _reference(contract, set(contract_by_id), where)

    components = _collection(system, "system", "components", {"id", "kind", "language", "depends_on", "data_sets", "implements", "provides", "requires"})
    component_ids = {r["id"] for r in components}
    for r in components:
        where = f"system.component {r['id']}"
        _text(r["kind"], f"{where}.kind")
        _text(r["language"], f"{where}.language")
        for field in ("depends_on", "data_sets", "implements", "provides"):
            r[field] = _names(r[field], f"{where}.{field}")
        for ref in r["implements"]:
            _reference(ref, requirement_ids, where)
        for ref in r["provides"]:
            _reference(ref, set(contract_by_id), where)
        requires = _list(r["requires"], f"{where}.requires")
        seen_reqs = set()
        for entry in requires:
            _shape(entry, {"contract_id", "accepted_revisions"}, f"{where}.requires")
            contract = _text(entry["contract_id"], f"{where}.requires.contract_id")
            if contract in seen_reqs:
                raise SpecError(f"{where}.requires contains duplicate contract {contract}")
            seen_reqs.add(contract)
            _reference(contract, set(contract_by_id), where)
            entry["accepted_revisions"] = _names(entry["accepted_revisions"], f"{where}.requires {contract}.accepted_revisions", True)
        r["requires"] = sorted(requires, key=lambda x: x["contract_id"])

    data_sets = _collection(data, "data", "data_sets", {"id", "owner", "schema_version", "invariants", "retention_days", "migration", "recovery"})
    data_ids = {r["id"] for r in data_sets}
    for r in data_sets:
        where = f"data.data_set {r['id']}"
        _reference(_text(r["owner"], f"{where}.owner"), component_ids, where)
        _integer(r["schema_version"], f"{where}.schema_version", 1)
        _integer(r["retention_days"], f"{where}.retention_days")
        r["invariants"] = _names(r["invariants"], f"{where}.invariants", True)
        migration = _shape(r["migration"], {"strategy", "rollback"}, f"{where}.migration")
        for field in migration:
            _text(migration[field], f"{where}.migration.{field}")
        recovery = _shape(r["recovery"], {"rpo_minutes", "rto_minutes", "backup_retention_days"}, f"{where}.recovery")
        for field, value in recovery.items():
            _integer(value, f"{where}.recovery.{field}", 1 if field == "backup_retention_days" else 0)
    for r in components:
        where = f"system.component {r['id']}"
        for ref in r["data_sets"]:
            _reference(ref, data_ids, where)
        for ref in r["depends_on"]:
            _reference(ref, component_ids, where)

    by_component = {r["id"]: r for r in components}
    for r in components:
        for entry in r["requires"]:
            contract = entry["contract_id"]
            providers = [dep for dep in r["depends_on"] if contract in by_component[dep]["provides"]]
            if len(providers) != 1:
                raise SpecError(f"system.component {r['id']}: contract {contract} needs exactly one dependency provider")
            if contract_by_id[contract]["revision"] not in entry["accepted_revisions"]:
                raise SpecError(f"system.component {r['id']}: contract {contract} revision is not accepted")

    blueprint_records = _list(blueprints["components"], "blueprints.components")
    blueprint_ids = set()
    bootstrap = []
    for r in blueprint_records:
        if not isinstance(r, dict):
            raise SpecError("blueprints.components entry must be an object")
        ident = _text(r.get("component_id"), "blueprints.component_id")
        where = f"blueprints.component {ident}"
        if ident in blueprint_ids:
            raise SpecError(f"{where}: duplicate blueprint")
        blueprint_ids.add(ident)
        _reference(ident, component_ids, where)
        mode = r.get("mode")
        if mode == "bootstrap":
            _shape(r, {"component_id", "mode", "source_path"}, where)
            source_path = _text(r["source_path"], f"{where}.source_path")
            from pathlib import PurePosixPath
            path = PurePosixPath(source_path)
            if path.is_absolute() or ".." in path.parts or "\\" in source_path:
                raise SpecError(f"{where}.source_path must be repository-relative without parent traversal")
            bootstrap.append(ident)
        elif mode == "generated":
            _shape(r, {"component_id", "mode", "generator", "toolchains", "inputs", "requirements", "contracts"}, where)
            generator = _shape(r["generator"], {"id", "version", "sha256"}, f"{where}.generator")
            _text(generator["id"], f"{where}.generator.id")
            _text(generator["version"], f"{where}.generator.version")
            generator["sha256"] = _digest(generator["sha256"], f"{where}.generator.sha256")
            if not isinstance(r["toolchains"], dict) or not r["toolchains"]:
                raise SpecError(f"{where}.toolchains must be a nonempty object")
            for tool, digest in r["toolchains"].items():
                _text(tool, f"{where}.toolchains key")
                r["toolchains"][tool] = _digest(digest, f"{where}.toolchains.{tool}")
            if not isinstance(r["inputs"], dict):
                raise SpecError(f"{where}.inputs must be an object")
            for field, allowed in (("requirements", requirement_ids), ("contracts", set(contract_by_id))):
                r[field] = _names(r[field], f"{where}.{field}")
                for ref in r[field]:
                    _reference(ref, allowed, where)
        else:
            raise SpecError(f"{where}.mode must be bootstrap or generated")
    for ident in component_ids - blueprint_ids:
        raise SpecError(f"missing blueprint for component {ident}")

    cases = _collection(verification, "verification", "cases", {"id", "requirement_ids", "target_component", "modality", "input", "expected"})
    for r in cases:
        where = f"verification.case {r['id']}"
        r["requirement_ids"] = _names(r["requirement_ids"], f"{where}.requirement_ids", True)
        for ref in r["requirement_ids"]:
            _reference(ref, requirement_ids, where)
        _reference(_text(r["target_component"], f"{where}.target_component"), component_ids, where)
        if r["modality"] not in ("cli", "service", "ui"):
            raise SpecError(f"{where}.modality is unsupported")
        expected = r["expected"]
        if not isinstance(expected, dict):
            raise SpecError(f"{where}.expected must be an object")
        if expected.get("kind") == "exact":
            _shape(expected, {"kind", "value"}, f"{where}.expected")
        elif expected.get("kind") == "rubric":
            _shape(expected, {"kind", "text"}, f"{where}.expected")
            _text(expected["text"], f"{where}.expected.text")
        else:
            raise SpecError(f"{where}.expected.kind is unsupported")
    for req in requirement_ids:
        if not any(req in r["implements"] for r in components):
            raise SpecError(f"requirement {req} has no implementing component")
        if not any(req in r["requirement_ids"] for r in cases):
            raise SpecError(f"requirement {req} has no acceptance case")

    projected = {"version": 1, "id": sources.id, "components": [
        {key: r[key] for key in ("id", "kind", "language", "depends_on", "data_sets")} for r in components
    ], "data_sets": [{"id": r["id"], "owner": r["owner"], "recovery": {key: r["recovery"][key] for key in ("rpo_minutes", "rto_minutes")}} for r in data_sets]}
    try:
        graph = parse_spec(projected)
    except SpecError as exc:
        raise SpecError(f"system/data: {exc}") from exc
    return ValidatedV2({"version": 2, "id": sources.id, "layers": layers}, graph, tuple(sorted(bootstrap)))
