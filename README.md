# Software management bootstrap kernel

This repository contains the bootstrap kernel for a spec-driven software management service. Its authoritative specification starts at `spec/solution.json` and resolves six linked layers covering product intent, behavior, components, data, blueprints, and verification. The component catalog is generated from that spec; the model and CLI remain hand-authored bootstrap code. Service and UI previews, release control, and production experiments described in the [design](docs/superpowers/specs/2026-10-03-spec-driven-software-management-design.md) are subsequent milestones.

Run from the repository root with Python 3.11 or later:

```bash
PYTHONPATH=src python3 -m specctl validate spec/solution.json
PYTHONPATH=src python3 -m specctl order spec/solution.json
PYTHONPATH=src python3 -m specctl impact spec/solution.json spec-model --direction consumers
PYTHONPATH=src python3 -m specctl resolve spec/solution.json
PYTHONPATH=src python3 -m specctl catalog spec-model
PYTHONPATH=src python3 -m specctl candidate verify-current
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

GitHub Actions runs these tests, self-spec commands, and current-candidate reconstruction on pull requests and pushes to `main`.

The resolved output includes exact source-byte digests, a semantic digest, and `bootstrap_components`. The generated catalog can be removed and reconstructed byte-for-byte from a committed spec revision and pinned generator and Python recipe:

```bash
PYTHONPATH=src python3 -m specctl candidate build spec/solution.json --revision "$(git rev-parse HEAD)"
PYTHONPATH=src python3 -m specctl candidate verify-current
PYTHONPATH=src python3 -m specctl catalog spec-model
```

The build writes `src/specctl/generated_catalog.py`, a candidate record under `.verity/candidates/`, and evidence from the catalog acceptance case and unit suite. Commit those outputs on the candidate branch. With a short-lived Triock GitHub App installation token stored in a mode-600 file, submit the clean branch for review:

```bash
PYTHONPATH=src python3 -m specctl candidate submit --branch feat/your-candidate --token-file /path/to/installation-token
```

Submission checks that the token is scoped only to `Triock/verity`, pushes the branch, and opens or reuses its PR. It does not merge or promote anything. The candidate record is review evidence, not a deployable release lock. `spec-model` and `specctl` still cannot be regenerated from the spec.

Release locking currently supports v1 specifications only. To exercise the legacy lock, supply a JSON object mapping **every** component ID to its built artifact's SHA-256 digest:

```bash
PYTHONPATH=src python3 -m specctl lock tests/fixtures/solution-v1.json artifacts.json
```

The v1 lock pins exact digests and the exact spec-file bytes. V2 locking must also pin the resolved digest and is not yet implemented. This kernel does not build artifacts, verify supplied digests against files, migrate data, or deploy a lock. Those operations must be added before a lock can authorize a real release.
