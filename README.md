# Software management bootstrap kernel

This repository contains the first runnable kernel for a spec-driven software management service. The service's own component graph is in `spec/solution.json`. It is currently a Python command-line program and library; the service, generator, preview system, release controller, and production experiments described in the [design](docs/superpowers/specs/2026-10-03-spec-driven-software-management-design.md) are subsequent milestones.

Run from the repository root with Python 3.11 or later:

```bash
PYTHONPATH=src python3 -m specctl validate spec/solution.json
PYTHONPATH=src python3 -m specctl order spec/solution.json
PYTHONPATH=src python3 -m specctl impact spec/solution.json spec-model --direction consumers
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

To create a release lock, supply a JSON object mapping **every** component ID to its built artifact's SHA-256 digest:

```bash
PYTHONPATH=src python3 -m specctl lock spec/solution.json artifacts.json
```

The lock pins exact digests and the exact spec-file bytes. This kernel does not build the artifacts, verify the supplied digests against files, migrate data, or deploy the lock. Those operations must be added before a lock can authorize a real release.
