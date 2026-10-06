"""Read the v2 index and its confined, versioned layer files."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .spec import SpecError, decode_json


LAYER_NAMES = ("product", "behavior", "system", "data", "blueprints", "verification")


@dataclass(frozen=True)
class V2Sources:
    id: str
    layers: dict[str, dict]
    source_sha256: dict[str, str]


def _keys(value: object, expected: set[str], location: str) -> dict:
    if not isinstance(value, dict):
        raise SpecError(f"{location} must be an object")
    missing = expected - value.keys()
    unknown = value.keys() - expected
    if missing or unknown:
        raise SpecError(f"{location}: missing {sorted(missing)}, unknown {sorted(unknown)}")
    return value


def _nonempty(value: object, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SpecError(f"{location} must be a nonempty string")
    return value


def _layer_path(root: Path, value: object, location: str) -> tuple[Path, str]:
    path = Path(_nonempty(value, location))
    if path.is_absolute():
        raise SpecError(f"{location} must be relative")
    if ".." in path.parts:
        raise SpecError(f"{location} has parent traversal")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root):
        raise SpecError(f"{location} escapes index directory")
    return resolved, path.as_posix()


def load_v2_sources(index_path: str | Path, index_bytes: bytes | None = None) -> V2Sources:
    """Load exact source bytes while rejecting path escapes and ambiguous JSON."""
    index = Path(index_path)
    root = index.parent.resolve()
    try:
        content = index.read_bytes() if index_bytes is None else index_bytes
    except OSError as exc:
        raise SpecError(f"{index}: {exc}") from exc
    raw = _keys(decode_json(content, str(index)), {"version", "id", "layers"}, str(index))
    if type(raw["version"]) is not int or raw["version"] != 2:
        raise SpecError(f"{index}: version must be 2")
    solution_id = _nonempty(raw["id"], f"{index}: id")
    paths = _keys(raw["layers"], set(LAYER_NAMES), f"{index}: layers")
    layers = {}
    digests = {index.name: hashlib.sha256(content).hexdigest()}
    seen = {index.name}
    for name in LAYER_NAMES:
        location = f"{index}: layers.{name}"
        path, relative = _layer_path(root, paths[name], location)
        if relative in seen:
            raise SpecError(f"{location} duplicates source path {relative}")
        seen.add(relative)
        try:
            layer_bytes = path.read_bytes()
        except OSError as exc:
            raise SpecError(f"{location}: {path}: {exc}") from exc
        layer = decode_json(layer_bytes, str(path))
        if not isinstance(layer, dict):
            raise SpecError(f"{path} must be an object")
        if type(layer.get("version")) is not int or layer["version"] != 1:
            raise SpecError(f"{path}: version must be 1")
        layers[name] = layer
        digests[relative] = hashlib.sha256(layer_bytes).hexdigest()
    return V2Sources(solution_id, layers, digests)
