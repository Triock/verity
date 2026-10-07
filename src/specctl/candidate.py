"""Pin and reconstruct generated catalog candidates from committed specifications."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from . import catalog_generator
from .spec import SpecError, decode_json
from .v2_resolve import canonical_bytes, resolve_v2


GENERATOR_PATH = "src/specctl/catalog_generator.py"
CATALOG_COMPONENT = "component-catalog"
CURRENT_POINTER = ".verity/candidates/current.json"


def _git(repo: Path, *args: str) -> bytes:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True)
    if result.returncode:
        raise SpecError(f"git {' '.join(args[:2])} failed: {result.stderr.decode(errors='replace').strip()}")
    return result.stdout


def _within(repo: Path, path: Path, label: str) -> str:
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError as exc:
        raise SpecError(f"{label} escapes repository") from exc


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _committed_bytes(repo: Path, revision: str, relative: str) -> bytes:
    return _git(repo, "show", f"{revision}:{relative}")


def _check_revision(repo: Path, revision: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise SpecError("revision must be a full 40-character Git commit SHA")
    resolved = _git(repo, "rev-parse", "--verify", f"{revision}^{{commit}}").decode().strip()
    if resolved != revision:
        raise SpecError("revision does not identify the requested commit")
    result = subprocess.run(["git", "merge-base", "--is-ancestor", revision, "HEAD"], cwd=repo, capture_output=True)
    if result.returncode:
        raise SpecError("revision is not reachable from current HEAD")


def _check_source(repo: Path, revision: str, path: Path, label: str) -> bytes:
    relative = _within(repo, path, label)
    try:
        current = path.read_bytes()
    except OSError as exc:
        raise SpecError(f"{label}: {exc}") from exc
    if current != _committed_bytes(repo, revision, relative):
        raise SpecError(f"{label} differs from revision {revision}")
    return current


def plan_candidate(index_path: Path, revision: str, repo: Path) -> dict:
    """Pin one catalog candidate to exact Git, spec, generator, and recipe bytes."""
    repo = Path(repo).resolve()
    index_path = Path(index_path).resolve()
    _check_revision(repo, revision)
    index_relative = _within(repo, index_path, "index")
    envelope = resolve_v2(index_path)
    for relative in envelope["source_sha256"]:
        source = index_path.parent / relative
        _check_source(repo, revision, source, relative)

    blueprints = [entry for entry in envelope["resolved"]["layers"]["blueprints"]["components"] if entry["component_id"] == CATALOG_COMPONENT]
    if len(blueprints) != 1 or blueprints[0]["mode"] != "generated":
        raise SpecError("component-catalog must have one generated blueprint")
    blueprint = blueprints[0]
    if blueprint["generator"]["id"] != catalog_generator.GENERATOR_ID or blueprint["generator"]["version"] != "1":
        raise SpecError("unsupported catalog generator")
    if blueprint["inputs"] != {"output_path": catalog_generator.OUTPUT_PATH}:
        raise SpecError("unsupported catalog output path")
    if set(blueprint["toolchains"]) != {"python-recipe"}:
        raise SpecError("catalog requires the python-recipe toolchain pin")
    generator_bytes = _check_source(repo, revision, repo / GENERATOR_PATH, GENERATOR_PATH)
    if _sha(generator_bytes) != blueprint["generator"]["sha256"]:
        raise SpecError("generator digest does not match pinned blueprint")
    active_generator = Path(catalog_generator.__file__).read_bytes()
    if _sha(active_generator) != blueprint["generator"]["sha256"]:
        raise SpecError("active generator digest differs from pinned blueprint")
    recipe_path = catalog_generator.TOOLCHAIN_PATH
    recipe_bytes = _check_source(repo, revision, repo / recipe_path, recipe_path)
    if _sha(recipe_bytes) != blueprint["toolchains"]["python-recipe"]:
        raise SpecError("toolchain recipe digest does not match pinned blueprint")
    recipe = decode_json(recipe_bytes, recipe_path)
    if recipe != {"version": 1, "language": "python", "minimum_version": "3.11", "dependencies": "standard-library-only", "encoding": "utf-8", "serialization": "canonical-json"}:
        raise SpecError("unsupported catalog toolchain recipe")
    if sys.version_info < (3, 11):
        raise SpecError("catalog generator requires Python 3.11 or newer")
    record = {
        "version": 1,
        "spec_revision": revision,
        "index_path": index_relative,
        "source_sha256": envelope["source_sha256"],
        "resolved_sha256": envelope["resolved_sha256"],
        "component_id": CATALOG_COMPONENT,
        "generator": {"id": blueprint["generator"]["id"], "sha256": blueprint["generator"]["sha256"]},
        "toolchains": blueprint["toolchains"],
    }
    record["candidate_id"] = _sha(canonical_bytes(record))
    return record


def _render_twice(index_path: Path) -> bytes:
    resolved = resolve_v2(index_path)["resolved"]
    with tempfile.TemporaryDirectory(prefix="catalog-first-") as first, tempfile.TemporaryDirectory(prefix="catalog-second-") as second:
        first_path = Path(first) / "generated_catalog.py"
        second_path = Path(second) / "generated_catalog.py"
        first_path.write_bytes(catalog_generator.generate_catalog(resolved))
        second_path.write_bytes(catalog_generator.generate_catalog(resolved))
        first_bytes = first_path.read_bytes()
        if first_bytes != second_path.read_bytes():
            raise SpecError("catalog generator produced different bytes on reconstruction")
        return first_bytes


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = canonical_bytes(value) + b"\n"
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as staged:
        staged.write(content)
        staged_name = staged.name
    os.replace(staged_name, path)


def build_candidate(index_path: Path, revision: str, repo: Path) -> dict:
    repo = Path(repo).resolve()
    index_path = Path(index_path).resolve()
    record = plan_candidate(index_path, revision, repo)
    generated = _render_twice(index_path)
    artifact_path = repo / catalog_generator.OUTPUT_PATH
    _within(repo, artifact_path, "artifact")
    record["artifact"] = {"path": catalog_generator.OUTPUT_PATH, "sha256": _sha(generated)}
    record_path = repo / ".verity" / "candidates" / record["candidate_id"] / "candidate.json"
    if record_path.exists() and decode_json(record_path.read_bytes(), str(record_path)) != record:
        raise SpecError("existing candidate record conflicts with pinned inputs")
    if artifact_path.exists() and artifact_path.read_bytes() != generated:
        raise SpecError("existing artifact conflicts with pinned candidate")
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=artifact_path.parent, delete=False) as staged:
        staged.write(generated)
        staged_name = staged.name
    os.replace(staged_name, artifact_path)
    _write_json(record_path, record)
    _write_json(repo / CURRENT_POINTER, {"candidate_id": record["candidate_id"]})
    evidence = evaluate_candidate(record, repo)
    _write_json(record_path.parent / "evidence.json", evidence)
    return record


def evaluate_candidate(record: dict, repo: Path) -> dict:
    """Run the catalog case and unit suite in fresh processes."""
    repo = Path(repo).resolve()
    resolved = resolve_v2(repo / record["index_path"])["resolved"]
    cases = [case for case in resolved["layers"]["verification"]["cases"] if case["id"] == "query-component-catalog"]
    if len(cases) != 1:
        raise SpecError("catalog acceptance case is missing or ambiguous")
    case = cases[0]
    if case["modality"] != "cli" or case["input"].get("command") != "catalog" or case["expected"].get("kind") != "exact":
        raise SpecError("catalog acceptance case is unsupported")
    component_id = case["input"].get("component_id")
    if not isinstance(component_id, str) or not component_id:
        raise SpecError("catalog acceptance input needs a component_id")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo / "src")
    command = [sys.executable, "-m", "specctl", "catalog", component_id]
    try:
        observed_run = subprocess.run(command, cwd=repo, env=env, capture_output=True, timeout=60)
    except subprocess.TimeoutExpired as exc:
        raise SpecError("catalog acceptance timed out") from exc
    if observed_run.returncode:
        raise SpecError("catalog acceptance command failed")
    observed = decode_json(observed_run.stdout, "catalog acceptance output")
    expected = case["expected"]["value"]
    if observed != expected:
        raise SpecError("catalog acceptance response differs from expected result")
    test_command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"]
    try:
        tests = subprocess.run(test_command, cwd=repo, env=env, capture_output=True, timeout=180)
    except subprocess.TimeoutExpired as exc:
        raise SpecError("candidate unit tests timed out") from exc
    if tests.returncode:
        raise SpecError("candidate unit tests failed")
    return {
        "version": 1,
        "candidate_id": record["candidate_id"],
        "status": "passed",
        "python_version": ".".join(str(part) for part in sys.version_info[:3]),
        "rebuild_sha256": record["artifact"]["sha256"],
        "acceptance": {"case_id": case["id"], "input": case["input"], "expected": expected, "observed": observed, "passed": True},
        "tests": {"command": "python -m unittest discover -s tests -q", "exit_code": tests.returncode, "stdout_sha256": _sha(tests.stdout), "stderr_sha256": _sha(tests.stderr)},
    }


def verify_current(repo: Path) -> dict:
    """Reconstruct current generated output from its pinned source revision."""
    repo = Path(repo).resolve()
    pointer_path = repo / CURRENT_POINTER
    try:
        pointer = decode_json(pointer_path.read_bytes(), str(pointer_path))
    except OSError as exc:
        raise SpecError(f"current candidate pointer is missing: {exc}") from exc
    if not isinstance(pointer, dict) or set(pointer) != {"candidate_id"} or not isinstance(pointer["candidate_id"], str) or not re.fullmatch(r"[0-9a-f]{64}", pointer["candidate_id"]):
        raise SpecError("invalid current candidate pointer")
    record_path = repo / ".verity" / "candidates" / pointer["candidate_id"] / "candidate.json"
    try:
        record = decode_json(record_path.read_bytes(), str(record_path))
    except OSError as exc:
        raise SpecError(f"candidate record is missing: {exc}") from exc
    if not isinstance(record, dict) or record.get("candidate_id") != pointer["candidate_id"]:
        raise SpecError("candidate record ID does not match current pointer")
    if not isinstance(record.get("index_path"), str) or not isinstance(record.get("spec_revision"), str):
        raise SpecError("candidate record has invalid index path or revision")
    planned = plan_candidate(repo / record["index_path"], record["spec_revision"], repo)
    if {key: value for key, value in record.items() if key != "artifact"} != planned:
        raise SpecError("candidate record differs from pinned revision")
    generated = _render_twice(repo / record["index_path"])
    if record.get("artifact") != {"path": catalog_generator.OUTPUT_PATH, "sha256": _sha(generated)}:
        raise SpecError("candidate artifact digest does not match reconstruction")
    artifact = repo / catalog_generator.OUTPUT_PATH
    if not artifact.exists() or artifact.read_bytes() != generated:
        raise SpecError("candidate artifact differs from reconstruction")
    evidence_path = repo / ".verity" / "candidates" / pointer["candidate_id"] / "evidence.json"
    try:
        evidence = decode_json(evidence_path.read_bytes(), str(evidence_path))
    except OSError as exc:
        raise SpecError(f"candidate evidence is missing: {exc}") from exc
    if not isinstance(evidence, dict) or evidence.get("candidate_id") != record["candidate_id"] or evidence.get("status") != "passed" or evidence.get("rebuild_sha256") != record["artifact"]["sha256"]:
        raise SpecError("candidate evidence does not identify a passing build")
    fresh = evaluate_candidate(record, repo)
    if evidence.get("acceptance") != fresh["acceptance"] or evidence.get("tests", {}).get("exit_code") != 0:
        raise SpecError("candidate evidence does not match current evaluation")
    return record
