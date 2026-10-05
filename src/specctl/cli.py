"""Command-line entry points for the bootstrap specification kernel."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from .graph import build_order, change_impact
from .release import ReleaseError, compile_release
from .spec import SpecError, decode_json, load_spec, parse_spec


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="specctl")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "order"):
        commands.add_parser(name).add_argument("spec")
    impact = commands.add_parser("impact")
    impact.add_argument("spec")
    impact.add_argument("component")
    impact.add_argument(
        "--direction", choices=("consumers", "dependencies", "both"), required=True
    )
    lock = commands.add_parser("lock")
    lock.add_argument("spec")
    lock.add_argument("artifacts_json")
    return parser


def _read_lock_inputs(spec_path: str, artifacts_path: str):
    source = Path(spec_path)
    inventory = Path(artifacts_path)
    try:
        spec_bytes = source.read_bytes()
        inventory_bytes = inventory.read_bytes()
    except OSError as exc:
        raise SpecError(f"cannot read lock inputs {source} and {inventory}: {exc}") from exc
    raw_spec = decode_json(spec_bytes, str(source))
    artifacts = decode_json(inventory_bytes, str(inventory))
    try:
        spec = parse_spec(raw_spec)
    except SpecError as exc:
        raise SpecError(f"{source}: {exc}") from exc
    return spec, hashlib.sha256(spec_bytes).hexdigest(), artifacts


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "lock":
            spec, spec_digest, artifacts = _read_lock_inputs(args.spec, args.artifacts_json)
            result = compile_release(spec, spec_digest, artifacts)
        else:
            spec = load_spec(args.spec)
            if args.command == "validate":
                result = {
                    "solution_id": spec.id,
                    "components": len(spec.components),
                    "data_sets": len(spec.data_sets),
                }
            elif args.command == "order":
                result = build_order(spec)
            else:
                result = change_impact(spec, args.component, args.direction)
    except (SpecError, ReleaseError) as exc:
        print(f"specctl: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0
