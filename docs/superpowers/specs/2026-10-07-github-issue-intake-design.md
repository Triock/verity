# GitHub Issues intake: first workflow input

## Decision and boundary

The first issue source for the management service is GitHub Issues in `Triock/verity`. The issue is a request, not accepted software behavior. The reviewed six-layer Software Specification remains authoritative. This slice reads one opted-in issue and records a reproducible snapshot in the working Git tree. It does not start generation, commit or push the snapshot, open a PR, mutate the GitHub issue, or promote a release. A later controller will commit and push an issue branch, then drive the candidate workflow.

The source adapter is deliberately separate from the snapshot store. Azure DevOps work items and in-app intake can later produce the same normalized input without changing the specification or candidate pipeline.

## Approaches considered

1. **GitHub Issues as the only store:** easy to start, but issue edits or deletion would erase the exact inputs used for a candidate and make restart reconciliation fragile.
2. **Private database as the first registry:** supports concurrent workers, but introduces a second durable store and backup/recovery obligations before an issue can be traced to a Git revision.
3. **GitHub source plus Git-tracked snapshots (selected):** preserve source provenance and exact observed inputs beside the spec. The first CLI writes the snapshot; the next controller slice commits and pushes it on an issue branch.

## Intake contract

`specctl issue import NUMBER --token-file PATH` obtains a short-lived GitHub App installation token from an owner-only mode-600 file. It verifies that the token sees exactly `Triock/verity`, then reads `GET /repos/Triock/verity/issues/NUMBER`. No issue text becomes a shell command, agent instruction, or automatic spec edit. The `verity:ready` label is an explicit triage gate. Only an open issue with that label is accepted; pull requests returned through the Issues API are rejected. The adapter does not request Issues write permission. The Triock App needs repository Issues **read-only** permission for live intake. Webhooks are a later optimization; the first controller can poll and reconcile.

The normalized snapshot includes schema version, source provider/repository/issue ID/number/URL/update time, title, body, and sorted labels. It excludes comments, attachments, arbitrary API fields, and credentials. The adapter accepts only the exact `Triock/verity` repository, positive integer IDs, HTTPS GitHub issue URLs for that repository and number, UTC update timestamps, bounded UTF-8 title/body, and distinct label names. It computes SHA-256 over canonical JSON to identify the snapshot.

## Git-tracked registry

The CLI writes `.verity/issues/github/<number>/snapshots/<digest>.json` and then atomically updates `.verity/issues/github/<number>/current.json`. It refuses to overwrite conflicting existing snapshot bytes. Importing the same observed revision is idempotent. An older `updated_at` value cannot replace a newer current snapshot. A per-issue local file lock serializes writers; the pointer is published last so a failed write leaves the prior current snapshot valid. The CLI reports the source reference, digest, and paths, and explicitly reports that the files are uncommitted until Git records and pushes them.

This is the first version of the `issue-snapshots` data set. The spec records its ownership, invariants, retention, migration strategy, and recovery targets. A successful Git commit and remote push will be the durability acknowledgment in the controller slice. Recovery from a remote Git ref and a restore drill are not claimed in this slice.

## Verification and acceptance

- An authorized, labeled GitHub Issue fixture is normalized and recorded at the expected digest and paths.
- Repeating that import leaves the snapshot and pointer byte-identical.
- A newer issue revision appends a snapshot and advances the pointer; a stale revision is rejected.
- Unlabeled, closed, malformed, cross-repository, pull-request, oversized, and token-scope-invalid inputs produce no current pointer change.
- A local process interruption during snapshot staging preserves the prior pointer.
- The six-layer self-spec links the new use case, requirement, `specctl` implementation, verification case, and `issue-snapshots` data contract. The generated component catalog is rebuilt from the new spec revision, and CI verifies the current candidate.
