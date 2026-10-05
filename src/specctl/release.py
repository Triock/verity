"""Compile complete, content-addressed solution release locks."""

from __future__ import annotations

import re

from .graph import build_order
from .spec import SolutionSpec


class ReleaseError(ValueError):
    """A release inventory cannot form a cohesive solution."""


def _digest(value: object, location: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-fA-F]{64}", value) is None:
        raise ReleaseError(f"{location} must be a 64-character SHA-256 digest")
    return value.lower()


def compile_release(
    spec: SolutionSpec, spec_sha256: str, artifacts: dict[str, str]
) -> dict:
    """Pin exactly one artifact for each specified component."""
    spec_digest = _digest(spec_sha256, "spec")
    if not isinstance(artifacts, dict):
        raise ReleaseError("artifacts must be a JSON object")
    components = {component.id: component for component in spec.components}
    missing = sorted(components.keys() - artifacts.keys())
    extra = sorted(artifacts.keys() - components.keys())
    if missing:
        raise ReleaseError(f"missing artifacts: {', '.join(missing)}")
    if extra:
        raise ReleaseError(f"extra artifacts: {', '.join(extra)}")
    digests = {
        component_id: _digest(artifacts[component_id], f"{component_id} artifact")
        for component_id in components
    }
    return {
        "format_version": 1,
        "solution_id": spec.id,
        "spec_sha256": spec_digest,
        "components": [
            {
                "id": component_id,
                "artifact_sha256": digests[component_id],
                "depends_on": list(components[component_id].depends_on),
            }
            for component_id in build_order(spec)
        ],
    }
