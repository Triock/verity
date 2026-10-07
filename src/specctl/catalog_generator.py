"""Deterministic generator for the specification-derived component catalog."""

from __future__ import annotations

from .v2_resolve import canonical_bytes


GENERATOR_ID = "component-catalog-v1"
OUTPUT_PATH = "src/specctl/generated_catalog.py"
TOOLCHAIN_PATH = "tools/catalog-python.json"


def generate_catalog(resolved: dict) -> bytes:
    """Render an importable catalog from validated v2 semantic input."""
    layers = resolved["layers"]
    contracts = {entry["id"]: entry["revision"] for entry in layers["behavior"]["contracts"]}
    records = {}
    for component in layers["system"]["components"]:
        records[component["id"]] = {
            "id": component["id"],
            "kind": component["kind"],
            "language": component["language"],
            "depends_on": sorted(component["depends_on"]),
            "data_sets": sorted(component["data_sets"]),
            "implements": sorted(component["implements"]),
            "provides": [
                {"contract_id": contract_id, "revision": contracts[contract_id]}
                for contract_id in sorted(component["provides"])
            ],
            "requires": sorted(component["requires"], key=lambda entry: entry["contract_id"]),
        }
    payload = canonical_bytes(records).decode("utf-8")
    return (
        '# Generated from the Software Specification. Attribution: Richard Hillman <triock@gmail.com>.\n'
        '"""Read-only component catalog generated from the resolved specification."""\n'
        'import json as _json\n\n'
        f'_CATALOG = _json.loads({payload!r})\n\n'
        'def list_components():\n'
        '    """Return stable component identifiers."""\n'
        '    return sorted(_CATALOG)\n\n'
        'def get_component(component_id):\n'
        '    """Return a declared component record, or None when absent."""\n'
        '    record = _CATALOG.get(component_id)\n'
        '    return None if record is None else _json.loads(_json.dumps(record))\n'
    ).encode("utf-8")
