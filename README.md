# Software management bootstrap kernel

This repository contains the first runnable kernel for a spec-driven software management service. Its authoritative specification starts at `spec/solution.json` and resolves six linked layers covering product intent, behavior, components, data, blueprints, and verification. The current implementation is a Python command-line program and library. Generation, preview environments, release control, and production experiments described in the [design](docs/superpowers/specs/2026-10-03-spec-driven-software-management-design.md) are subsequent milestones.

Run from the repository root with Python 3.11 or later:

```bash
PYTHONPATH=src python3 -m specctl validate spec/solution.json
PYTHONPATH=src python3 -m specctl order spec/solution.json
PYTHONPATH=src python3 -m specctl impact spec/solution.json spec-model --direction consumers
PYTHONPATH=src python3 -m specctl resolve spec/solution.json
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

GitHub Actions runs these tests and self-spec commands on pull requests and pushes to `main`.

The resolved output includes exact source-byte digests, a semantic digest, and `bootstrap_components`. Both current components are hand-authored bootstrap code and are **not yet regenerable**. A future generator must turn their blueprints into reproducible implementation inputs.

Release locking currently supports v1 specifications only. To exercise the legacy lock, supply a JSON object mapping **every** component ID to its built artifact's SHA-256 digest:

```bash
PYTHONPATH=src python3 -m specctl lock tests/fixtures/solution-v1.json artifacts.json
```

The v1 lock pins exact digests and the exact spec-file bytes. V2 locking must also pin the resolved digest and is not yet implemented. This kernel does not build artifacts, verify supplied digests against files, migrate data, or deploy a lock. Those operations must be added before a lock can authorize a real release.
