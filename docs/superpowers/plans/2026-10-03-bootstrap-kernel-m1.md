# Bootstrap Kernel Milestone 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a runnable spec kernel that validates the management service's own component graph, calculates change impact, and locks a cohesive release set.

**Architecture:** A dependency-free Python package reads a versioned JSON manifest. A validator establishes graph and data-contract invariants; a graph planner calculates affected components; a release compiler pins artifact digests for a complete compatible set. The CLI exposes these functions so a later reconciler can call them without a UI or external service.

**Tech Stack:** Python 3.11+ standard library, JSON, `unittest`, Git.

**Spec:** `docs/superpowers/specs/2026-10-03-spec-driven-software-management-design.md`, especially “Layered specification,” “Dependency and compatibility graph,” and “Self-hosting bootstrap.” This plan implements the first kernel slice of that wider design; generation, preview evaluation, production promotion, and recovery are subsequent milestones.

## Global Constraints

- Production data remains outside generated source; the manifest records data ownership and recovery requirements.
- Every component has a stable ID and explicit dependencies.
- A release set includes all components and pins exact artifact digests.
- No external Python dependencies are needed for this seed kernel.
- Errors must identify the offending manifest field or component.

## File map

- `src/specctl/spec.py`: load and validate the versioned manifest into immutable component and dataset records.
- `src/specctl/graph.py`: dependency order and bidirectional impact closure.
- `src/specctl/release.py`: validate artifact inventory and compile a cohesive release lock.
- `src/specctl/cli.py`, `src/specctl/__main__.py`: command-line interface and JSON output.
- `spec/solution.json`: first machine-readable specification of the management service.
- `tests/test_spec.py`, `tests/test_graph.py`, `tests/test_release.py`, `tests/test_cli.py`: behavioral checks.
- `README.md`: run commands and the limit of this milestone.

### Task 1: Versioned spec and validation

**Files:** Create `src/specctl/__init__.py`, `src/specctl/spec.py`, `spec/solution.json`, `tests/test_spec.py`.

**Interfaces:** `load_spec(path: str | Path) -> SolutionSpec`; `parse_spec(raw: dict) -> SolutionSpec`; `Component(id: str, kind: str, language: str, depends_on: tuple[str, ...], data_sets: tuple[str, ...])`; `DataSet(id: str, owner: str, recovery: RecoveryPolicy)`; `SolutionSpec(version: int, id: str, components: tuple[Component, ...], data_sets: tuple[DataSet, ...])`. `SpecError(ValueError)` names the invalid field.

- [ ] **Step 1: Write failing tests.** Cover a valid self-spec, duplicate component IDs, unknown dependency, dependency cycle, unknown dataset ownership, and missing `recovery` fields. Use minimal in-memory dictionaries in `tests/test_spec.py` and `parse_spec` for invalid cases. For example:

  ```python
  with self.assertRaisesRegex(SpecError, 'duplicate component'):
      parse_spec({**valid_spec, 'components': [valid_spec['components'][0]] * 2})
  ```
- [ ] **Step 2: Run `PYTHONPATH=src python3 -m unittest tests.test_spec -v`.** Verify failure because `specctl.spec` is absent.
- [ ] **Step 3: Implement the model and parser.** Require `version == 1`, a nonempty solution ID, component kinds `application|service|library|infrastructure`, unique nonempty IDs, dependency references, acyclic graph, dataset owner references, and recovery fields `rpo_minutes` and `rto_minutes` as nonnegative integers. Reject a component's reference to an unknown dataset. Load JSON with `Path.read_text` and `json.loads`; translate JSON and I/O errors to `SpecError` with the file path. Use immutable records:

  ```python
  @dataclass(frozen=True)
  class Component:
      id: str
      kind: str
      language: str
      depends_on: tuple[str, ...]
      data_sets: tuple[str, ...]
  ```

- [ ] **Step 4: Write `spec/solution.json`.** Describe only the current `specctl` application and `spec-model` library, with `specctl` depending on `spec-model`. Keep `data_sets` empty until the workflow store is implemented. Data-contract validation is exercised with test fixtures.
- [ ] **Step 5: Run the test command again, then commit** the task as `feat: define versioned solution spec`.

### Task 2: Dependency and requirement impact

**Files:** Create `src/specctl/graph.py`, `tests/test_graph.py`.

**Interfaces:** `build_order(spec: SolutionSpec) -> tuple[str, ...]` returns dependencies before consumers with lexicographic tie breaking. `change_impact(spec: SolutionSpec, component_id: str, direction: Literal['consumers', 'dependencies', 'both']) -> tuple[str, ...]` includes the starting component and returns IDs in build order.

- [ ] **Step 1: Write failing tests.** A foundation-library change reaches its service and application consumers; an application requirement reaches its dependencies; `both` includes both directions transitively; unknown IDs and directions raise `SpecError`; build order is stable independent of input ordering. The central assertion is:

  ```python
  self.assertEqual(change_impact(spec, 'foundation', 'consumers'),
                   ('foundation', 'service', 'app'))
  ```
- [ ] **Step 2: Run `PYTHONPATH=src python3 -m unittest tests.test_graph -v`.** Verify failure because `specctl.graph` is absent.
- [ ] **Step 3: Implement adjacency maps and deterministic topological sorting.** Detect cycles defensively even though Task 1 rejects them. Walk forward dependency edges for `dependencies`, reverse edges for `consumers`, and both edge sets for `both`. Use a lexicographically sorted ready set:

  ```python
  ready = sorted(component_id for component_id, count in indegree.items() if count == 0)
  while ready:
      component_id = ready.pop(0)
      order.append(component_id)
      for consumer in sorted(consumers[component_id]):
          indegree[consumer] -= 1
          if indegree[consumer] == 0:
              bisect.insort(ready, consumer)
  ```
- [ ] **Step 4: Run the graph and spec tests, then commit** as `feat: calculate component change impact`.

### Task 3: Cohesive release lock

**Files:** Create `src/specctl/release.py`, `tests/test_release.py`.

**Interfaces:** `compile_release(spec: SolutionSpec, spec_sha256: str, artifacts: dict[str, str]) -> dict`. The result has `format_version`, `solution_id`, `spec_sha256`, and `components`, where each component entry has `id`, `artifact_sha256`, and `depends_on`, sorted in build order. `ReleaseError(ValueError)` names missing, extra, or malformed artifacts.

- [ ] **Step 1: Write failing tests.** A valid inventory produces a stable lock for every component; a missing or extra component and a digest that is not exactly 64 hexadecimal characters fail. Reordering input dictionary keys does not change canonical JSON bytes (`json.dumps(lock, sort_keys=True, separators=(',', ':'))`). For example:

  ```python
  self.assertEqual([entry['id'] for entry in lock['components']],
                   ['foundation', 'service', 'app'])
  ```
- [ ] **Step 2: Run `PYTHONPATH=src python3 -m unittest tests.test_release -v`.** Verify failure because `specctl.release` is absent.
- [ ] **Step 3: Implement inventory validation and release compilation.** Include every component, including libraries and infrastructure, because this first lock is a complete system set. Validate `spec_sha256` with the same digest rule. Do not infer compatibility from a version number; exact digests are required. Construct entries in `build_order(spec)` order:

  ```python
  {'id': component_id,
   'artifact_sha256': artifacts[component_id],
   'depends_on': list(component.depends_on)}
  ```
- [ ] **Step 4: Run all three test modules, then commit** as `feat: compile cohesive release locks`.

### Task 4: CLI and first self-spec verification

**Files:** Create `src/specctl/cli.py`, `src/specctl/__main__.py`, `tests/test_cli.py`, `README.md`.

**Interfaces:** `main(argv: list[str] | None = None) -> int`. Commands: `validate SPEC`; `order SPEC`; `impact SPEC COMPONENT --direction consumers|dependencies|both`; `lock SPEC ARTIFACTS_JSON`. Standard output is canonical JSON, diagnostics go to standard error, and invalid inputs return exit code 2. `lock` computes the SHA-256 of the exact spec file bytes and reads an artifact inventory JSON object.

- [ ] **Step 1: Write failing CLI tests.** Exercise the committed `spec/solution.json` with `validate`, `order`, and `impact`; check a malformed manifest produces code 2 and an actionable diagnostic; use a temporary artifact inventory to verify `lock` includes all components. Capture output around `main`:

  ```python
  with redirect_stdout(stdout), redirect_stderr(stderr):
      code = main(['impact', 'spec/solution.json', 'spec-model',
                   '--direction', 'consumers'])
  self.assertEqual(code, 0)
  self.assertEqual(json.loads(stdout.getvalue()), ['spec-model', 'specctl'])
  ```
- [ ] **Step 2: Run `PYTHONPATH=src python3 -m unittest tests.test_cli -v`.** Verify failure because the CLI is absent.
- [ ] **Step 3: Implement `argparse` commands and error conversion.** Print `json.dumps(..., sort_keys=True, separators=(',', ':'))`; avoid partial output on failure. Keep the entry point minimal:

  ```python
  if __name__ == '__main__':
      raise SystemExit(main())
  ```
- [ ] **Step 4: Document exact commands and current limitations in `README.md`.** State that this kernel is the first self-spec reader and release planner, not yet a generator or production controller.
- [ ] **Step 5: Run `PYTHONPATH=src python3 -m unittest discover -s tests -v`, `PYTHONPATH=src python3 -m specctl validate spec/solution.json`, and `git diff --check`.** Commit as `feat: expose spec kernel CLI` only after all succeed.

## Milestone acceptance

- The management service's own manifest validates using its own kernel.
- A change to `spec-model` identifies its dependent components; a requirement from `specctl` identifies foundation dependencies.
- A release lock cannot omit, add, or ambiguously version a component.
- All commands work from a clean checkout with Python 3.11+ and no installed packages.
- Later milestones can add generation and self-upgrade without changing the v1 manifest's authority boundary.
