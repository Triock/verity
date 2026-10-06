# Layered Specification Resolution V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate six versioned specification layers and emit a canonical, content-addressed resolved input while preserving v1 behavior.

**Architecture:** A strict file loader reads a v2 index and confined layer files. A semantic validator resolves stable IDs, graph edges, contracts, data requirements, blueprints, and acceptance cases. A canonicalizer emits source-byte digests and a semantic digest for future generation. The existing CLI dispatches by version; v1 remains readable.

**Tech Stack:** Python 3.11+ standard library, JSON, `unittest`, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-06-layered-spec-resolution-design.md` and `docs/superpowers/specs/2026-10-03-spec-driven-software-management-design.md`.

## Global constraints

- Preserve the existing public v1 `parse_spec`, `load_spec`, `build_order`, `change_impact`, and release-lock behavior for v1 inputs.
- Do not infer runtime compatibility from version labels or mark hand-authored components regenerable.
- All layer file paths are relative to the v2 index directory and confined beneath it, including after symlink resolution. Bootstrap `source_path` values are repository-relative metadata; reject absolute paths and parent traversal, but they may point outside `spec/`.
- Reject unknown fields, duplicate JSON keys, duplicate stable IDs, missing pins, and unresolved references with file and record context.
- The resolver performs no Git write, network call, generation, secret lookup, or deployment.
- All commits use Richard Hillman <triock@gmail.com> as author and committer.

## V2 wire format

`spec/solution.json` is `{"version":2,"id":"software-manager","layers":{"product":"product.json","behavior":"behavior.json","system":"system.json","data":"data.json","blueprints":"blueprints.json","verification":"verification.json"}}`. Each layer has `"version":1` and exactly the named collection fields below.

| Layer | Collections and record fields |
| --- | --- |
| `product` | `actors`: `{id,name}`; `use_cases`: `{id,actor_id,goal}` |
| `behavior` | `requirements`: `{id,use_case_id,statement,contract_ids}`; `contracts`: `{id,revision,description}` |
| `system` | `components`: `{id,kind,language,depends_on,data_sets,implements,provides,requires}`; `requires` entries are `{contract_id,accepted_revisions}` |
| `data` | `data_sets`: `{id,owner,schema_version,invariants,retention_days,migration,recovery}`; `migration` is `{strategy,rollback}`; `recovery` is `{rpo_minutes,rto_minutes,backup_retention_days}` |
| `blueprints` | `components`: either `{component_id,mode:"bootstrap",source_path}` or `{component_id,mode:"generated",generator:{id,version,sha256},toolchains,inputs,requirements,contracts}` |
| `verification` | `cases`: `{id,requirement_ids,target_component,modality,input,expected}`; `modality` is `cli`, `service`, or `ui`; `expected` is `{kind:"exact",value:...}` or `{kind:"rubric",text:...}` |

IDs, descriptive strings, revisions, migration text, and source paths are nonempty strings. Collection IDs are unique within their kind. String-reference arrays are unique. `schema_version` and `backup_retention_days` are positive integers; `retention_days`, `rpo_minutes`, and `rto_minutes` are nonnegative integers. `generator.sha256` and every `toolchains` value are 64 hexadecimal characters and normalized to lowercase in resolved output. `inputs` is a JSON object. `invariants` is a nonempty list of nonempty strings for a dataset. The current self-spec has no datasets, so nonempty data behavior must be covered by fixtures.

Every requirement names an existing use case and has at least one implementing component and one acceptance case. Every contract named by a requirement or component exists. A component providing a contract is its provider; a required contract has exactly one provider among that component's declared dependencies, and the contract's revision appears in its `accepted_revisions`. Every component has exactly one blueprint. Blueprint requirement and contract references must exist. The graph remains acyclic and dataset owners/references remain valid. These checks validate declarations; they do not prove runtime compatibility.

## File map

- `src/specctl/v2_source.py`: strict index/layer loading, path confinement, exact source digests.
- `src/specctl/v2_validate.py`: record shapes, stable references, graph and data checks; returns a validated semantic model.
- `src/specctl/v2_resolve.py`: canonical ordering, semantic digest, public `resolve_v2` interface.
- `src/specctl/cli.py`: version dispatch, `resolve`, v2 `validate/order/impact`, explicit v2 lock rejection.
- `spec/solution.json`, `spec/{product,behavior,system,data,blueprints,verification}.json`: authoritative v2 self-spec.
- `tests/fixtures/solution-v1.json`: legacy v1 fixture for regression and lock tests.
- `tests/test_v2_source.py`, `tests/test_v2_validate.py`, `tests/test_v2_resolve.py`, `tests/test_cli.py`: behavioral tests.
- `README.md`, `.github/workflows/ci.yml`: commands and CI checks.

### Task 1: Strict v2 source loading

**Files:** Create `src/specctl/v2_source.py`, `tests/test_v2_source.py`.

**Interfaces:** `V2Sources(id: str, layers: dict[str, dict], source_sha256: dict[str, str])`; `load_v2_sources(index_path: str | Path, index_bytes: bytes | None = None) -> V2Sources`. The optional bytes let CLI dispatch without rereading the index.

- [ ] Write tests using a temporary `spec/` directory with all six minimal layer files. Assert exact source digests, duplicate-key rejection, missing layer, absolute path, `..`, and a symlink that escapes the index directory. The failure assertion for traversal is:

  ```python
  with self.assertRaisesRegex(SpecError, "layers.product.*parent traversal"):
      load_v2_sources(index_path)
  ```

- [ ] Run `PYTHONPATH=src python3 -m unittest tests.test_v2_source -v`; confirm it fails because the loader is absent.
- [ ] Implement an exact-key index parser, require `version == 2`, load paths below `index_path.parent.resolve()`, call existing `decode_json` for every file, and hash the exact bytes before parsing. Reject any path with `..`, an absolute path, or a resolved target outside the index directory. Name source digest keys `solution.json` and each normalized layer filename.
- [ ] Run the focused tests, then commit `feat: load confined v2 specification layers`.

### Task 2: Semantic validation and graph projection

**Files:** Create `src/specctl/v2_validate.py`, `tests/test_v2_validate.py`.

**Interfaces:** `ValidatedV2(resolved: dict, graph: SolutionSpec, bootstrap_components: tuple[str, ...])`; `validate_v2(sources: V2Sources) -> ValidatedV2`. `resolved` is a normalized semantic document with `version`, `id`, and all six layers. `graph` projects system components and data recovery into existing `SolutionSpec` records for `build_order` and `change_impact`.

- [ ] Write tests for one fully linked generated component and one bootstrap component. Check unknown use case, requirement, contract, dataset, owner, acceptance target, blueprint component, missing blueprint, duplicate IDs, dependency cycle, missing data migration/recovery field, invalid generator/toolchain digest, and provider/revision mismatch. A representative check is:

  ```python
  bundle.layers["system"]["components"][0]["implements"] = ["missing-requirement"]
  with self.assertRaisesRegex(SpecError, "missing-requirement"):
      validate_v2(bundle)
  ```

- [ ] Run `PYTHONPATH=src python3 -m unittest tests.test_v2_validate -v`; confirm a missing-module failure.
- [ ] Implement small exact-key and type helpers; validate every record against the wire-format table; gather ID maps; enforce cross-layer references and cardinality; transform system/data into a v1-shaped dictionary and call `parse_spec` for graph, owner, dataset, and cycle checks. Prefix errors with the layer and offending ID. Treat booleans as invalid integers.
- [ ] Run source and validation tests, then commit `feat: validate linked v2 specification`.

### Task 3: Canonical semantic resolution

**Files:** Create `src/specctl/v2_resolve.py`, `tests/test_v2_resolve.py`.

**Interfaces:** `canonical_bytes(value: object) -> bytes`; `resolve_v2(index_path: str | Path, index_bytes: bytes | None = None) -> dict` returns `{source_sha256,resolved,resolved_sha256,bootstrap_components}`. Use `json.dumps(value,sort_keys=True,separators=(",", ":"),ensure_ascii=False).encode("utf-8")`.

- [ ] Write tests that permute record order, set-like reference order, JSON whitespace, and mixed-case digests. Assert identical `resolved_sha256` but different source digests where bytes changed. Change a requirement statement, contract revision, or generator digest and assert a different resolved digest. Confirm bootstrap IDs are sorted and the resolver never says they are generated.
- [ ] Run `PYTHONPATH=src python3 -m unittest tests.test_v2_resolve -v`; confirm a missing-module failure.
- [ ] In `validate_v2`, normalize set-like reference arrays and digest case; in `resolve_v2`, order components by `build_order`, other record collections by stable ID, `requires` by contract ID, and `accepted_revisions` lexicographically. Hash only `resolved`, not source paths or formatting, for `resolved_sha256`.
- [ ] Run all three v2 test modules, then commit `feat: resolve canonical v2 generation input`.

### Task 4: CLI dispatch and v1 regression

**Files:** Modify `src/specctl/cli.py`, `tests/test_cli.py`; add `tests/test_v2_cli.py`.

**Interfaces:** Existing v1 command output remains byte-for-byte stable. `validate`, `order`, and `impact` accept v2; `resolve INDEX` accepts v2 and prints the envelope. `lock` explicitly rejects v2 with exit code 2 and `v2 release locks are not supported yet` on standard error.

- [ ] Write CLI tests for v2 `validate/order/impact/resolve`, v1 `resolve` rejection, v2 `lock` rejection, and unchanged v1 output. For example:

  ```python
  code = main(["resolve", str(v2_index)])
  self.assertEqual(code, 0)
  self.assertEqual(json.loads(stdout.getvalue())["resolved"]["version"], 2)
  ```

- [ ] Run `PYTHONPATH=src python3 -m unittest tests.test_cli tests.test_v2_cli -v`; confirm the new command tests fail.
- [ ] Read the index bytes once, decode its version, dispatch v1 to `parse_spec` and v2 to `validate_v2(load_v2_sources(...))`; call `resolve_v2` for the envelope. Keep diagnostics on standard error and canonical JSON on standard output. Preserve v1 lock path and add the explicit v2 rejection before `parse_spec`.
- [ ] Run all CLI and v2 tests, then commit `feat: expose v2 validation and resolution CLI`.

### Task 5: Authoritative self-spec and CI

**Files:** Replace `spec/solution.json`; create six layer files; create `tests/fixtures/solution-v1.json`; modify existing tests, `README.md`, `.github/workflows/ci.yml`.

**Interfaces:** `spec/solution.json` is the v2 authority. The v1 fixture is for regression only. The current `spec-model` library and `specctl` application each have a `bootstrap` blueprint with source paths; no component is described as regenerated yet.

- [ ] Add self-spec tests asserting two components, a linked product use case, requirement, contract, acceptance case, and both bootstrap blueprints. Move v1-specific release-lock and CLI assertions to the v1 fixture. Confirm the new self-spec tests fail before replacing the files.
- [ ] Write the v2 index and six small layers using the wire format above. Keep `data_sets` empty until workflow state exists. Link `specctl` to `spec-model` through a provided/required contract and record explicit accepted revision.
- [ ] Update README to show `validate`, `order`, `impact`, and `resolve` on the v2 self-spec; show `lock` only with the v1 fixture and explain the temporary v2 lock gap. Update CI to run `resolve` as well as tests and current self-spec commands.
- [ ] Run `PYTHONPATH=src python3 -m unittest discover -s tests -v`, `PYTHONPATH=src python3 -m specctl validate spec/solution.json`, `PYTHONPATH=src python3 -m specctl resolve spec/solution.json`, and `git diff --check`. Confirm the output lists both components as bootstrap and contains a 64-character resolved digest. Commit `feat: define layered v2 self-spec`.

## Milestone acceptance

- V1 parser, graph, CLI, and release-lock fixtures remain green.
- V2 source loading confines every layer to the index directory and hashes exact bytes.
- V2 validation connects product intent, behavior, system, data, blueprints, and verification; malformed or ambiguous references fail clearly.
- Resolved semantic bytes are stable across formatting and nonsemantic ordering; meaningful changes alter the digest.
- The management service's own v2 spec resolves from a clean checkout and truthfully reports bootstrap components.
- CI runs the new checks. No code-generation or promotion claim is made at this milestone.
