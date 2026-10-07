# Seed Candidate Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn one committed v2 self-spec revision into a pinned, rebuildable generated catalog, executable evidence, and a PR submitted through the Triock GitHub App.

**Architecture:** Extend the six-layer self-spec with a generated catalog component. A small allowlisted generator emits a Python module from resolved spec input. A seed candidate command checks Git provenance and pins, reconstructs in isolation, runs the catalog acceptance case and tests, and writes candidate/evidence records. A separate submit command checks the scoped App token and Git branch before pushing and opening a PR.

**Tech Stack:** Python 3.11+ standard library, JSON, Git CLI, GitHub REST API, `unittest`, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-07-seed-candidate-loop-design.md` and `docs/superpowers/specs/2026-10-03-spec-driven-software-management-design.md`.

## Global Constraints

- Author and committer of every commit: Richard Hillman <triock@gmail.com>. Documentation, generated headers, release metadata, and PR credits use the same attribution.
- The v2 spec is authority; generated Python and candidate records are rebuildable outputs. `spec-model` and `specctl` remain bootstrap.
- No secret values enter the spec, generated source, candidate record, evidence, or logs. GitHub authentication is a short-lived Triock App installation token read from a protected file.
- A candidate is not a release. Never merge or promote it automatically.
- Preserve v1 fixture behavior and existing v2 validation/resolve output for unchanged inputs.
- Fail closed on stale Git revisions, dirty spec or tool sources, digest mismatches, wrong Git remote, wrong installation repository scope, failed evaluation, or ambiguous PR state.

## File map and wire contracts

| File | Responsibility |
| --- | --- |
| `spec/{product,behavior,system,blueprints,verification}.json` | Add catalog use case, requirement, contract, component, blueprint, and exact acceptance case. |
| `tools/catalog-python.json` | Checked-in Python standard-library toolchain recipe; its exact SHA-256 is the blueprint pin. |
| `src/specctl/catalog_generator.py` | Allowlisted `component-catalog-v1` generator; `generate_catalog(resolved: dict) -> bytes`. |
| `src/specctl/generated_catalog.py` | Regenerable Python output with `list_components()` and `get_component(id)`. |
| `src/specctl/candidate.py` | Git provenance, candidate record, generation, clean rebuild, evaluation, and verification. |
| `src/specctl/candidate_publish.py` | Token scope, exact origin/branch checks, push, and GitHub PR creation. |
| `src/specctl/cli.py` | `catalog`, `candidate build`, `candidate verify-current`, and `candidate submit`. |
| `.verity/candidates/<id>/{candidate,evidence}.json` | Pinned candidate and observed evaluation. |
| `.verity/candidates/current.json` | `{ "candidate_id": "<64-hex>" }`; CI verifies only current output. |
| `tests/test_catalog_generator.py`, `tests/test_candidate.py`, `tests/test_candidate_publish.py`, `tests/test_cli.py` | Behavior checks using temporary Git repositories and a local HTTP server where remote behavior matters. |
| `.github/workflows/ci.yml`, `README.md` | Run current candidate verification and document regeneration and review commands. |

Candidate record v1 keys: `version`, `candidate_id`, `spec_revision`, `index_path`, `source_sha256`, `resolved_sha256`, `component_id`, `generator` (`id`, `sha256`), `toolchains`, `artifact` (`path`, `sha256`). Candidate ID is SHA-256 of canonical JSON of the same object before adding `candidate_id` and `artifact`. Evidence v1 keys: `version`, `candidate_id`, `status`, `python_version`, `rebuild_sha256`, `acceptance` (`case_id`, `input`, `expected`, `observed`, `passed`), `tests` (`command`, `exit_code`, `stdout_sha256`, `stderr_sha256`). Evidence is observational and is not part of candidate identity.

### Task 1: Declare and generate the catalog component

**Files:** Modify the self-spec; create `tools/catalog-python.json`, `src/specctl/catalog_generator.py`, `tests/test_catalog_generator.py`; update `tests/test_self_spec_v2.py`.

**Interfaces:** `generate_catalog(resolved: dict) -> bytes` emits UTF-8 Python with a stable `CATALOG` object and functions `list_components()` and `get_component(component_id)`. The generator includes no file I/O. Its source bytes and toolchain recipe bytes are SHA-256 pinned in `spec/blueprints.json`.

- [ ] Write failing tests that pass a resolved fixture to `generate_catalog`, execute the emitted module in a new Python process, and assert a component query matches an independent literal. Add a self-spec test that expects `component-catalog` to be the only generated component and `specctl` to depend on it. Run `PYTHONPATH=src python3 -m unittest tests.test_catalog_generator tests.test_self_spec_v2 -v` and observe failure for the missing generator/component.
- [ ] Add product use case `inspect-catalog`, behavior requirement `query-catalog`, contract `catalog-query` revision 1, generated `component-catalog` library depending on `spec-model`, `specctl` dependency and accepted contract revision, and an exact CLI case querying `spec-model`. Add a small Python recipe file recording minimum version `3.11`, standard-library-only generation, UTF-8, and canonical JSON. Implement the pure generator so it emits only system-layer component declarations, with JSON embedded as a quoted string and no `eval`.
- [ ] Compute exact SHA-256 for generator source and recipe; put them in the blueprint. Run `validate` and `resolve` on the self-spec and the focused tests. Commit `feat: specify and generate component catalog`.

### Task 2: Pin Git revision and build candidate records

**Files:** Create `src/specctl/candidate.py`, `tests/test_candidate.py`.

**Interfaces:** `plan_candidate(index_path: Path, revision: str, repo: Path) -> dict` returns the record before artifact fields. `build_candidate(index_path: Path, revision: str, repo: Path) -> dict` writes the generated module and records, returning the completed record. `verify_current(repo: Path) -> dict` checks the pointer and reconstructs the generated module byte-for-byte without writing.

- [ ] Write a temporary Git-repository fixture containing the six-layer spec, generator, and recipe. Write failing tests that assert a full 40-hex revision and exact source-byte checks, reject an edited layer or generator pin, reject a revision outside the current branch history, and verify candidate ID and artifact SHA are stable. Run `PYTHONPATH=src python3 -m unittest tests.test_candidate -v` and observe the missing API failure.
- [ ] Implement `git rev-parse --verify`, `git merge-base --is-ancestor`, and `git show REV:PATH` with argument arrays and captured errors. Require the index, each layer, generator, and recipe to be under `repo`; compare committed bytes with working bytes before generation. Require `component-catalog-v1` and exact generator/toolchain digests. Compute the candidate ID from canonical JSON without artifact fields.
- [ ] Generate twice in distinct temporary directories and compare exact bytes. Atomically write `src/specctl/generated_catalog.py`, candidate record, and current pointer only after checks succeed; reject a conflicting existing candidate record. `verify_current` regenerates to memory and compares exact artifact bytes and record fields. Run focused tests and commit `feat: pin and rebuild catalog candidates`.

### Task 3: Run and record candidate evaluation

**Files:** Extend `src/specctl/candidate.py`; create `tests/test_candidate_evaluation.py`; modify `src/specctl/cli.py`, `tests/test_cli.py`.

**Interfaces:** `evaluate_candidate(record: dict, repo: Path) -> dict` runs the exact `query-catalog` acceptance case in a new Python process and `python -m unittest discover -s tests -q`, recording observed values, process exit codes, and output digests. `catalog COMPONENT_ID` prints the generated catalog record as canonical JSON. `candidate build` writes evidence only when checks pass; `candidate verify-current` re-evaluates and rejects failed or mismatched evidence.

- [ ] Write failing tests for the CLI response after generation, missing generated module diagnostic, passing acceptance evidence, a changed expected response, and a failing unit suite that does not leave passing evidence. Run focused tests and observe failures for the absent CLI/evaluator.
- [ ] Add CLI commands and implement evaluation with `subprocess.run` argument lists, explicit `cwd=repo`, `PYTHONPATH=repo/src`, a bounded timeout, and no shell. Parse the acceptance case from resolved verification layer; compare exact JSON response to `expected.value`. Record both observed and expected values, pass/fail, Python version, stdout/stderr digests, and unit-suite exit code. Do not write `status: passed` on any failure.
- [ ] Run focused and full tests; commit `feat: evaluate generated catalog candidates`.

### Task 4: Submit PR with scoped App token

**Files:** Create `src/specctl/candidate_publish.py`, `tests/test_candidate_publish.py`; extend `src/specctl/cli.py`.

**Interfaces:** `submit_candidate(repo: Path, token_path: Path, branch: str, base: str = "main") -> str` returns the PR URL. It reads current candidate/evidence and requires both tracked in `HEAD`, a clean worktree, current branch match, and exact `origin=https://github.com/Triock/verity.git`. It checks `GET /installation/repositories` returns only `Triock/verity`, then pushes the branch using temporary `GIT_ASKPASS`, and creates or returns an existing PR through the GitHub REST API.

- [ ] Write tests for wrong repository scope, dirty branch, missing evidence, and a repeated submission that returns an existing PR URL. Use a local HTTP server for GitHub API behavior and a temporary Git repository for local preflight. Run focused tests and observe the missing API failure.
- [ ] Implement HTTP requests with `urllib.request`, no token in URL or output; use a protected temporary directory for askpass and token copy; check API response owner/repo and existing PR head/base before POST. Ensure all Git commands use argument arrays and `GIT_TERMINAL_PROMPT=0`. Add the CLI submit subcommand, preserving exit code 2 for actionable errors.
- [ ] Run focused and full tests; commit `feat: submit candidates through scoped app token`.

### Task 5: Dogfood one candidate and CI

**Files:** Generate `src/specctl/generated_catalog.py`, `.verity/candidates/current.json`, `.verity/candidates/<id>/{candidate,evidence}.json`; update `.github/workflows/ci.yml`, `README.md`.

- [ ] Add a CI step running `python -m specctl candidate verify-current` after the unit suite, with full Git history available, and document `candidate build`, `catalog`, `verify-current`, and `submit` with exact commands and the distinction between candidate and release. Run CI-equivalent commands locally before generating the candidate to confirm the expected missing-candidate failure.
- [ ] Commit all authoritative source and tool changes first. Run `candidate build spec/solution.json --revision <that commit SHA>` and inspect the generated module, record, and evidence. Delete the generated module in a disposable copy, rebuild from the pinned revision, and compare SHA-256 byte-for-byte. Commit only the generated artifact and evidence as Richard.
- [ ] Run `PYTHONPATH=src python3 -m unittest discover -s tests -q`, `PYTHONPATH=src python3 -m specctl candidate verify-current`, `PYTHONPATH=src python3 -m specctl catalog spec-model`, and `git diff --check`. Review the full branch, fix findings, then use the scoped Triock App to push and submit a PR with the candidate evidence. Confirm PR CI passes; leave it open for human review.

## Milestone acceptance

- One generated self-component is runnable and can be recreated byte-for-byte from its pinned spec and tools.
- The candidate record proves source revision, semantic digest, generator, recipe, and artifact identity; evidence includes executed tests and actual CLI output.
- An App-scoped PR is open for human review with passing CI. No automatic merge, promotion, service/UI preview, or production mutation is claimed.
