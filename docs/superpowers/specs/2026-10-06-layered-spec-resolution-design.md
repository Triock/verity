# Layered specification resolution: bootstrap design

## Purpose and scope

The current v1 manifest validates a component graph and recovery targets. It cannot yet describe why a component exists, which contracts it satisfies, how to regenerate it, or what evidence should be collected. The next kernel slice will resolve versioned specification layers into one canonical input for a future generator. It will not generate code, change production data, or promote a release.

This slice finishes the specification foundation needed by the seed controller. The controller's Git workflow, durable workflow store, service, admin frontend, preview environment, and independent supervisor are subsequent slices of the self-hosting milestone.

## Approaches considered

1. **One larger JSON manifest:** simplest to parse, but changes to unrelated product, data, and implementation concerns collide in one file and become hard to review.
2. **An index with layer files (selected):** keeps each concern reviewable and permits one resolver to validate references across layers. It adds path and multi-file consistency checks, which belong in the kernel.
3. **Separate repositories per layer:** allows independent access controls but makes atomic cross-layer revisions and candidate review harder before the controller exists.

## Repository boundary

For the bootstrap, the index and its layers stay under `spec/` in `Triock/verity`. The resolver accepts a path to an index and has no hard-coded remote or repository layout. A later repository binding can point it at a dedicated specification checkout without changing layer semantics.

Only the specification files are authoritative for desired behavior. Generated code and release artifacts retain references to the exact Git specification revision and resolved digest. The v1 manifest remains readable by the existing commands; v2 files do not silently change v1 semantics.

## V2 layer layout

`spec/solution.json` becomes a version 2 index with a solution ID and exactly one relative path for each required layer:

| Layer | File | Initial records |
| --- | --- | --- |
| Product intent | `spec/product.json` | Actors, goals, use cases, stable IDs |
| Behavior | `spec/behavior.json` | Requirements and interface contracts with stable IDs |
| System | `spec/system.json` | Components, dependencies, contract references, dataset references, compatibility constraints |
| Data | `spec/data.json` | Dataset owner, schema version, invariants, retention, migration policy, backup and recovery targets |
| Blueprints | `spec/blueprints.json` | One implementation blueprint per component |
| Verification | `spec/verification.json` | Acceptance cases linked to requirements and the component or interface they exercise |

The index resolves only files beneath its own `spec/` directory. Absolute paths, parent traversal, symlink escapes, duplicate JSON keys, and duplicate stable IDs are errors. Layer files have their own `version` and record type; unknown fields, missing required fields, and unknown references fail with the file and record ID in the diagnostic. Array order is not semantic where records have stable IDs.

Each blueprint declares a component ID and one of two states:

- `bootstrap`: existing hand-authored code with a recorded source path and an explicit `regenerable: false` result. This records the present gap without claiming a clean rebuild is possible.
- `generated`: a generator ID, immutable generator digest, toolchain digests, input values, and referenced requirement and contract IDs. The resolver rejects missing pins or unknown references. A later generator must consume only this resolved input and declared external inputs.

There is exactly one blueprint for every component. A component's dependency and compatibility references must resolve within the same candidate specification. Data contracts cannot omit migration and recovery requirements, even when a current release has no migration to run. Secrets appear only as references to an external secret source, never as values in a layer file or resolved output.

An acceptance case declares its stable ID, requirement IDs, target component or interface, input, and expected result or review rubric. The resolver checks these references and preserves the case; execution belongs to the later evaluation service. Compatibility declarations name the provided or required contract revision explicitly. Resolution checks that declarations refer to existing contracts; it does not infer runtime compatibility or authorize a mixed release.

## Resolution contract

`specctl validate INDEX` accepts v1 or v2. For v2 it parses all layers, checks cross-layer references, cycles, ownership, compatibility declarations, and data requirements before reporting counts. Existing v1 behavior and CLI output remain stable.

`specctl resolve INDEX` accepts v2 and emits a JSON envelope containing:

- `source_sha256`: SHA-256 digests of the exact bytes of the index and each layer, keyed by normalized relative path;
- `resolved`: a canonical semantic document with records sorted by stable ID, dependency build order, normalized digest case, and no machine-specific paths;
- `resolved_sha256`: SHA-256 of the canonical JSON bytes of `resolved` (sorted keys, compact separators, UTF-8).

Whitespace or record order changes may alter a source digest but must not alter `resolved_sha256` when semantics are identical. A behavior, contract, blueprint, or compatibility change must alter the resolved digest. The output also lists components still in `bootstrap` state; it never reports the solution as fully regenerable while that list is nonempty. A future release manifest will pin both the exact source revision and resolved digest.

The resolver performs no Git writes, remote calls, code generation, secret lookup, or deployment. This keeps validation deterministic and usable on a PR without elevated credentials.

## Acceptance and transition

- The management service has a small v2 self-spec spanning all six layers. Its current two components are truthfully marked `bootstrap` until generators exist.
- The v2 self-spec validates and resolves from a clean checkout. Reordering keyed records or formatting JSON leaves the resolved digest unchanged; changing a requirement or blueprint changes it.
- Tests reject unknown references, duplicate IDs or keys, dependency cycles, path escapes, missing generator pins, and incomplete data contracts with actionable diagnostics.
- Existing v1 fixture loading, CLI commands, and release-lock tests continue to pass. The release-lock CLI remains v1-only until it can pin v2 source and resolved digests correctly; it must give an explicit unsupported-version error for v2.
- CI runs v1 regression tests and v2 validation and resolution checks. A clean reconstruction is still a later gate, after at least one generated component and the seed controller exist.

The next slice uses this resolver to plan a candidate from a spec commit, records the exact source and resolved digests, generates one bounded self-component, and opens a PR with runnable evaluation evidence.
