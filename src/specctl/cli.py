"""Command-line entry points for the bootstrap specification kernel."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from .graph import build_order, change_impact
from .candidate import build_candidate, verify_current
from .candidate_publish import ORIGIN, _git, submit_candidate
from .github_issues import fetch_issue
from .issue_registry import record_issue
from .release import ReleaseError, compile_release
from .spec import SpecError, decode_json, parse_spec
from .v2_resolve import resolve_v2
from .v2_source import load_v2_sources
from .v2_validate import validate_v2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="specctl")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "order", "resolve"):
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
    catalog = commands.add_parser("catalog")
    catalog.add_argument("component")
    candidate = commands.add_parser("candidate")
    candidate_commands = candidate.add_subparsers(dest="candidate_command", required=True)
    build = candidate_commands.add_parser("build")
    build.add_argument("index")
    build.add_argument("--revision", required=True)
    candidate_commands.add_parser("verify-current")
    submit = candidate_commands.add_parser("submit")
    submit.add_argument("--branch", required=True)
    submit.add_argument("--token-file", required=True)
    issue = commands.add_parser("issue")
    issue_commands = issue.add_subparsers(dest="issue_command", required=True)
    issue_import = issue_commands.add_parser("import")
    issue_import.add_argument("number", type=int)
    issue_import.add_argument("--token-file", required=True)
    return parser


def _read_lock_inputs(spec_path: str, artifacts_path: str):
    source = Path(spec_path)
    inventory = Path(artifacts_path)
    try:
        spec_bytes = source.read_bytes()
    except OSError as exc:
        raise SpecError(f"cannot read lock input {source}: {exc}") from exc
    raw_spec = decode_json(spec_bytes, str(source))
    if isinstance(raw_spec, dict) and raw_spec.get("version") == 2:
        raise SpecError("v2 release locks are not supported yet")
    try:
        inventory_bytes = inventory.read_bytes()
    except OSError as exc:
        raise SpecError(f"cannot read lock input {inventory}: {exc}") from exc
    artifacts = decode_json(inventory_bytes, str(inventory))
    try:
        spec = parse_spec(raw_spec)
    except SpecError as exc:
        raise SpecError(f"{source}: {exc}") from exc
    return spec, hashlib.sha256(spec_bytes).hexdigest(), artifacts


def _read_spec(path: str):
    source = Path(path)
    try:
        content = source.read_bytes()
    except OSError as exc:
        raise SpecError(f"{source}: {exc}") from exc
    raw = decode_json(content, str(source))
    version = raw.get("version") if isinstance(raw, dict) else None
    if version == 2 and type(version) is int:
        return validate_v2(load_v2_sources(source, content)).graph, content
    try:
        return parse_spec(raw), content
    except SpecError as exc:
        raise SpecError(f"{source}: {exc}") from exc


def _issue_repo() -> Path:
    checkout = Path.cwd()
    root = Path(_git(checkout, "rev-parse", "--show-toplevel").decode().strip())
    if _git(root, "remote", "get-url", "--all", "origin").decode().splitlines() != [ORIGIN]:
        raise SpecError("issue import requires a Triock/verity origin")
    if _git(root, "remote", "get-url", "--all", "--push", "origin").decode().splitlines() != [ORIGIN]:
        raise SpecError("issue import requires a Triock/verity push URL")
    return root


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "issue":
            result = record_issue(_issue_repo(), fetch_issue(args.number, Path(args.token_file)))
        elif args.command == "catalog":
            try:
                from .generated_catalog import get_component
            except ModuleNotFoundError as exc:
                if exc.name != "specctl.generated_catalog":
                    raise
                raise SpecError("generated catalog is missing; run specctl candidate build") from exc
            result = get_component(args.component)
            if result is None:
                raise SpecError(f"unknown catalog component: {args.component}")
        elif args.command == "candidate":
            if args.candidate_command == "build":
                result = build_candidate(Path(args.index), args.revision, Path.cwd())
            elif args.candidate_command == "verify-current":
                result = verify_current(Path.cwd())
            else:
                result = {"pr_url": submit_candidate(Path.cwd(), Path(args.token_file), args.branch)}
        elif args.command == "lock":
            spec, spec_digest, artifacts = _read_lock_inputs(args.spec, args.artifacts_json)
            result = compile_release(spec, spec_digest, artifacts)
        else:
            spec, content = _read_spec(args.spec)
            if args.command == "resolve":
                raw = decode_json(content, args.spec)
                if raw["version"] != 2:
                    raise SpecError("resolve requires a v2 specification")
                result = resolve_v2(args.spec, content)
            elif args.command == "validate":
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
