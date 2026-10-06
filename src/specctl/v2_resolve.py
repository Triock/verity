"""Produce stable, content-addressed semantic input from a v2 specification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .graph import build_order
from .v2_source import load_v2_sources
from .v2_validate import validate_v2


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def resolve_v2(index_path: str | Path, index_bytes: bytes | None = None) -> dict:
    sources = load_v2_sources(index_path, index_bytes)
    validated = validate_v2(sources)
    resolved = validated.resolved
    layers = resolved["layers"]
    for name, field in (
        ("product", "actors"), ("product", "use_cases"),
        ("behavior", "requirements"), ("behavior", "contracts"),
        ("data", "data_sets"), ("verification", "cases"),
    ):
        layers[name][field].sort(key=lambda record: record["id"])
    order = {component_id: index for index, component_id in enumerate(build_order(validated.graph))}
    layers["system"]["components"].sort(key=lambda record: order[record["id"]])
    layers["blueprints"]["components"].sort(key=lambda record: order[record["component_id"]])
    for blueprint in layers["blueprints"]["components"]:
        blueprint["regenerable"] = blueprint["mode"] == "generated"
    return {
        "source_sha256": sources.source_sha256,
        "resolved": resolved,
        "resolved_sha256": hashlib.sha256(canonical_bytes(resolved)).hexdigest(),
        "bootstrap_components": list(validated.bootstrap_components),
    }
