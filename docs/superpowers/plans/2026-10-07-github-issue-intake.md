# GitHub Issues Intake Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read an opted-in `Triock/verity` GitHub Issue into a normalized, Git-trackable, append-only local snapshot with no automatic execution.

**Architecture:** Keep the GitHub API reader, normalization rules, and local snapshot writer as separate units. `specctl issue import` coordinates them. The current issue source stays GitHub, while snapshots in `.verity/issues/` record exact observed input; the next controller slice will commit and push an issue branch.

**Tech Stack:** Python 3.11+ standard library, six-layer v2 JSON specification, Git, unittest, GitHub App installation token.

**Spec:** `docs/superpowers/specs/2026-10-07-github-issue-intake-design.md`, based on `docs/superpowers/specs/2026-10-03-spec-driven-software-management-design.md` at main `36d87d40c99df67fabcbf2460f47ab676af8ffba`.

## Global Constraints

- Repository fixed to `Triock/verity`; App token must see exactly that selected repository.
- Import only open non-PR issues with `verity:ready`; issue content is data, never an instruction to execute.
- Snapshot files are local and uncommitted until a later Git operation; CLI must say so.
- No issue mutation, webhook, automatic generation, PR, or release in this slice.
- Git author and committer for every commit: Richard Hillman <triock@gmail.com>.

---

## File structure

- `spec/{product,behavior,system,data,verification}.json`: linked issue-intake requirement, acceptance, and data contract; `spec/blueprints.json` remains bootstrap for `specctl`.
- `src/specctl/github_issues.py`: GitHub App token read, scoped HTTP fetch, and strict normalization.
- `src/specctl/issue_registry.py`: per-issue snapshot and pointer writing, stale-revision and symlink checks.
- `src/specctl/cli.py`: `issue import` entry point and JSON result.
- `tests/test_github_issues.py`, `tests/test_issue_registry.py`, `tests/test_issue_cli.py`: behavioral fixtures and regressions.
- `README.md`: operator command, permission, and current durability boundary.
- `.verity/candidates/`, `src/specctl/generated_catalog.py`: rebuilt catalog candidate after spec revision.

### Task 1: Specify intake behavior and data

**Files:** Modify `spec/product.json`, `spec/behavior.json`, `spec/system.json`, `spec/data.json`, `spec/verification.json`; test `tests/test_self_spec_v2.py`.

**Interfaces:** `specctl` implements `import-github-issue`, provides contract `issue-intake`, owns data set `issue-snapshots`; verification case `record-ready-github-issue` targets `specctl`.

- [ ] Add a failing self-spec test that resolves v2 and asserts the new use case, requirement, contract, dataset owner, and CLI acceptance case.
- [ ] Run `PYTHONPATH=src python3 -m unittest tests.test_self_spec_v2 -q` and confirm the new assertion fails.
- [ ] Add linked records: actor `issue-maintainer`, use case `capture-issue`, requirement `import-github-issue`, contract `issue-intake` revision 1, `specctl` implementation/provider/dataset, and exact dataset migration/recovery fields. Add a rubric acceptance case describing an open `verity:ready` issue producing one immutable snapshot and current pointer.
- [ ] Run the self-spec test and `PYTHONPATH=src python3 -m specctl resolve spec/solution.json`; commit as Richard.

### Task 2: Read and normalize a GitHub Issue

**Files:** Create `src/specctl/github_issues.py`, `tests/test_github_issues.py`.

**Interfaces:** `normalize_issue(raw: object, number: int) -> dict` returns a versioned snapshot; `fetch_issue(number: int, token_path: Path, api_call=_api) -> dict` checks the token and repository scope before fetching and normalizing.

- [ ] Write tests with fake API responses for a ready issue, closed/unlabeled/PR rejection, mismatched IDs/URL, duplicate labels, oversized text, malformed timestamp, and token scope failure. Use a mode-600 temporary token file; do not call live GitHub.
- [ ] Run `PYTHONPATH=src python3 -m unittest tests.test_github_issues -q` and confirm missing functions fail.
- [ ] Implement exact shape/length validation and canonical normalization. Reuse `candidate_publish._token` and `_api` only for the authentication/API boundary; do not duplicate token handling. Fetch only `/installation/repositories` and `/repos/Triock/verity/issues/NUMBER`.
- [ ] Run focused tests, then the full suite; commit as Richard.

### Task 3: Record immutable snapshots and expose CLI

**Files:** Create `src/specctl/issue_registry.py`, `tests/test_issue_registry.py`, `tests/test_issue_cli.py`; modify `src/specctl/cli.py`.

**Interfaces:** `record_issue(repo: Path, snapshot: dict) -> dict` writes `snapshots/<sha256>.json` then `current.json`, returns `{source,digest,snapshot_path,current_path,committed:false}`; CLI `issue import NUMBER --token-file PATH` calls `fetch_issue` then `record_issue`.

- [ ] Write registry tests for first import, exact replay, newer revision, stale revision, conflicting bytes, and a failed staged write preserving the prior pointer. Write CLI tests patching only `fetch_issue` and use real temporary snapshot files.
- [ ] Run focused tests and confirm missing behavior fails.
- [ ] Implement atomic writes with `tempfile` + `os.replace`, an owner-only `fcntl` lock, strict integer-derived paths, and no symlink traversal. Publish the pointer last. Add parser branch and JSON output.
- [ ] Run focused and full suites, then commit as Richard.

### Task 4: Rebuild candidate and prepare review

**Files:** Modify `README.md`, `src/specctl/generated_catalog.py`, `.verity/candidates/current.json`; create new `.verity/candidates/<id>/{candidate,evidence}.json`.

**Interfaces:** `specctl candidate build spec/solution.json --revision FULL_SHA` and `candidate verify-current` remain the reconstruction gate.

- [ ] Document the command, GitHub App Issues read-only permission, label gate, and need to commit/push snapshot files before claiming remote durability.
- [ ] Commit all code and spec changes, delete the old generated catalog module, and run `candidate build` pinned to the new full HEAD SHA. The old candidate remains historical; the pointer advances to the new one.
- [ ] Run all unit tests, `candidate verify-current`, `git diff --check`, and a clean-clone delete/rebuild with matching generated SHA-256; commit artifacts as Richard.
- [ ] Independently review the branch. Submit a PR to `Triock/verity` with requirements, candidate revision, exact tests, and the live Issues permission limitation. Do not merge.

## Self-review

All design requirements map to Tasks 1–4. This plan intentionally does not add a running controller or remote issue-branch durability; those belong to the next slice after the first source adapter and local registry work.
