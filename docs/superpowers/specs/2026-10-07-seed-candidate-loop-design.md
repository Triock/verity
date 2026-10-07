# Seed candidate loop: pinned catalog generation and review

## Decision and scope

The next bootstrap slice will take one committed revision of the software management system's own specification through a pinned generation, a clean reconstruction, executable evaluation, and a pull request. The generated component is a read-only component catalog consumed by the `specctl catalog` command. The accepted specification remains authoritative; the generated module and candidate record are replaceable outputs.

This slice does not promote a release, replace either existing bootstrap component, operate a service or UI preview, or store durable workflow state. A candidate PR is reviewable but is not a deployable solution release. The known-good `main` implementation stays available while the candidate is reviewed.

## Approaches considered

1. **Generate an entire existing CLI:** demonstrates a large self-rebuild, but the current blueprint lacks enough algorithm detail to regenerate validation and graph behavior faithfully.
2. **Generate a component catalog (selected):** creates executable, spec-derived code with a useful read path for the controller. Its small interface makes byte-for-byte reconstruction and submitted-input evaluation practical.
3. **Generate only documentation:** easiest to render, but it would not exercise a runnable self-component.

## Specification change

The v2 self-spec gains a `component-catalog` library and a `catalog-query` contract. A new requirement states that a caller can inspect a component's declared kind, language, dependencies, provided and required contracts, and dataset IDs. `specctl` depends on that component and accepts contract revision 1. A CLI acceptance case queries a known component and has an exact expected response. The catalog has a `generated` blueprint; `spec-model` and `specctl` remain `bootstrap`.

The generated blueprint uses generator ID `component-catalog-v1`, the SHA-256 of the checked-in generator source, and the SHA-256 of the checked-in Python toolchain recipe. The recipe defines the supported Python standard-library runtime and output rules. The build checks both pinned digests before running the allowlisted generator. The exact interpreter version is recorded in evidence; the recipe digest is not misrepresented as an interpreter binary digest.

The generated module lives at `src/specctl/generated_catalog.py`. It exports `get_component(component_id)` and `list_components()` and contains only values derived from the resolved v2 system layer. `specctl catalog COMPONENT_ID` executes it and returns JSON. A missing generated module gives a direct rebuild instruction.

## Candidate identity and reconstruction

`specctl candidate build INDEX --revision SHA` requires a full Git commit SHA reachable from the current checkout. It verifies that every index and layer file's bytes at `SHA` match the files being resolved, that the allowlisted generator and toolchain recipe at `SHA` match their blueprint digests, and that the relevant specification is valid. It rejects dirty authoritative inputs, changed pins, unsupported generators, path escapes, and an existing output that conflicts with the candidate. It never reads secret values.

The candidate record stores schema version, spec revision, all exact source digests, resolved digest, component ID, generator and toolchain digests, generated artifact path and digest, and a candidate ID derived from the canonical pre-artifact inputs. It is written beneath `.verity/candidates/<candidate-id>/candidate.json`; `.verity/candidates/current.json` names the active candidate for CI. Older records are retained as review history, while CI verifies the current pointer against the current generated module. The generated module is written at its fixed path. No data set or production state is changed.

The builder generates twice in separate temporary directories from the same resolved input and compares exact bytes. It then runs a fresh Python process against the candidate catalog, executes the catalog acceptance case's submitted input, and runs the repository unit suite. The evidence record contains the commands, exit status, observed response, expected response, output digests, Python version, and outcome. A failure is reported as failure; it is not written as passing evidence. The generated module can be deleted and reconstructed from the same spec revision and pinned tools with identical bytes.

The candidate record is a review artifact, not a release lock. It does not authorize deployment. V2 release locking remains separate work requiring complete artifact and compatibility pins.

## Git and PR boundary

The operator runs the builder on a feature branch based on the accepted `main` revision, commits the generated module and candidate evidence as Richard Hillman <triock@gmail.com>, pushes through the Triock GitHub App installation, and opens a PR with the spec commit, candidate ID, artifact digest, tests, observed acceptance result, and remaining bootstrap components. The repository includes a `candidate submit` command that accepts a short-lived GitHub App installation token through a protected file, verifies the token is scoped only to `Triock/verity`, verifies the exact `origin` and clean branch, pushes that branch, and creates the PR. It does not merge or promote it.

No private key or installation token is committed or printed. The command's remote write uses only the selected repository and never uses the `RichardHillman-Aderant` account. Repeated submission detects an existing PR for the same branch rather than creating duplicates. Human review occurs after CI and the runnable evidence are available.

## Acceptance

- The self-spec validates with three components, with only `component-catalog` marked generated.
- A generated module deleted from a checkout is reconstructed byte-for-byte from the recorded spec revision and pins.
- `specctl catalog spec-model` returns the spec-declared fields and the exact acceptance case passes in a fresh process.
- The candidate record pins the full spec revision, exact layer bytes, resolved digest, generator, toolchain recipe, and artifact digest; mismatches fail before publication.
- Evidence records successful unit tests and observed CLI behavior. CI repeats the build and verification on the PR.
- The Triock App submits a PR for human review with linked evidence. No automatic merge or production promotion occurs.
