---
name: verity-change-workflow
description: Use when changing Verity's specification, implementation, verification, release process, or GitHub pull request workflow.
---

# Verity change workflow

The accepted Software Specification defines desired behavior. Implementation and release artifacts must be traceable to it. Read the [design](../../docs/superpowers/specs/2026-10-03-spec-driven-software-management-design.md) and the current machine-readable spec, if present, before changing behavior. During bootstrap, the accepted design governs verification and operations; `spec/solution.json` v1 models only components and data sets. A missing field in that JSON does not by itself mean a requirement is missing.

## Decide what must change

1. Identify the requirement, contract, or operational rule governing the request. Cite its current revision in the change record.
2. If the requirement is missing or wrong across the accepted spec layers, revise the appropriate layer before making a lasting implementation change. Record acceptance checks and affected component IDs.
3. If code violates a correct spec, keep that spec and add a regression check for the correction. If CI or repository configuration implements an existing design rule, cite that rule without adding a duplicate requirement. For example, the first test workflow implements the design's PR evaluation rule; the absence of a CI field in `spec/solution.json` v1 does not require a spec edit.
4. Trace dependencies and consumers. Use `specctl impact` when the machine-readable spec supports the affected components. For data changes, include contracts, migration, recovery, and compatibility effects.

## Prepare review evidence

- Link the spec revision, affected components, implementation commit, checks, and observed results in the PR. State any preview or evaluation capability that is not yet implemented.
- Verify the candidate with the tests and runnable evaluation available at this stage. Human review follows the observed results; a code review remains available.
- Keep complete release sets and data integrity gates in view when changing deployment behavior. Do not present a component mix as a deployable release without compatibility evidence.

## Verify GitHub identity before writes

- Confirm `origin` is `Triock/verity`, the GitHub App installation belongs to `Triock` and includes `verity`, and the App has permission for the intended write. If authentication points to `RichardHillman-Aderant`, stop that GitHub write and use the approved Triock App path.
- Confirm Git author and committer are `Richard Hillman <triock@gmail.com>` and follow `AGENTS.md` for all other attribution. A GitHub App may appear as the automation actor while commit metadata remains Richard's.
- Pushing a branch, opening a PR, merging, and promoting a release are distinct actions. Perform only those authorized for the current task and policy.
