# Durable GitHub Issue workflow: first controller step

## Scope and authority

This design extends the accepted [software management design](2026-10-03-spec-driven-software-management-design.md) and [GitHub Issue intake design](2026-10-07-github-issue-intake-design.md). A GitHub Issue remains untrusted input. Only a reviewed Software Specification changes desired behavior. This slice takes one ready Issue through a durable, resumable Git branch and stops at `awaiting-spec`. It does not interpret the issue, edit the spec, generate code, open a PR, merge, or deploy.

## Approaches

1. Persist only in GitHub Issues: edits and deletion can erase the exact observed input.
2. Add a workflow database: useful for concurrent workers, but adds a second recovery system before the first durable handoff.
3. Persist snapshot and workflow state in a Git branch (selected): one remote commit pins source input and restart state; Git protects updates with fast-forward rules.

## Command and Git boundary

`specctl issue start NUMBER --token-file PATH` runs in a clean `Triock/verity` checkout on `main`, or on its existing `verity/issue-NUMBER` branch. The command checks that fetch and push URLs identify only the approved repository and that Git author and committer metadata are Richard Hillman <triock@gmail.com>. The installation token must be owner-only, scoped to exactly `Triock/verity`, and have Issues read and Contents write permissions. It never prints the token.

The controller fetches and validates the ready issue before changing branches. It authenticates to Git and checks that local `main` matches remote `main` from either entry branch, then creates or resumes `verity/issue-NUMBER`. An existing branch is accepted only if its workflow record identifies the same repository, issue ID, and branch. Before publication it validates the committed snapshot, pointer, and workflow bytes. Remote branch updates must descend from the observed ref and use an exact expected-ref lease, including an empty-ref lease on creation; no history rewrite or merge is allowed. The command confirms the remote branch SHA equals the local commit before reporting `durable: true`.

The controller allows only its own issue snapshot, pointer, and workflow record as pending files on its issue branch. This permits retry after interruption between file write and commit. It rejects unrelated worktree changes and unrelated commits between the recorded base revision and branch head. Only controller paths are staged and committed. The issue title and body are never used as shell commands or commit-message text.

## Workflow data and recovery

The existing immutable snapshot and current pointer remain under `.verity/issues/github/NUMBER/`. A versioned `.verity/issues/github/NUMBER/workflow.json` records the base revision, fixed branch, source issue ID, current digest, and `awaiting-spec` stage. The file and snapshot commit together. The controller verifies committed workflow digest and snapshot bytes before any update. A repeated run with the same issue revision makes no new commit and confirms the remote SHA. A newer issue revision appends a snapshot and advances both current pointer and workflow in one commit. The registry rejects an older source revision.

If the process stops before push, the local branch retains its commit; repeating the command pushes it. If it stops after push, repeating confirms the existing remote commit. A clean clone can fetch the branch and resume from its committed workflow record. A remote branch with missing or conflicting workflow state is rejected. Recovery from the remote Git ref is a verifiable procedure; a broader backup restore drill remains future work.

## Acceptance checks

- A ready issue produces a Richard-attributed commit with snapshot, pointer, and workflow record on `verity/issue-NUMBER`; a confirmed remote SHA is reported as durable.
- Repeating the same issue creates no extra commit. A newer revision appends a snapshot and advances the branch; an older revision is rejected.
- A failed push or remote mismatch never reports durability; retry resumes without force. A clean clone can fetch and resume the branch.
- Wrong origin, wrong account, unready issue, mismatched existing workflow, unrelated dirty files, and incorrect Git identity are rejected before a GitHub write.
- The six-layer self-spec links the use case, requirement, contract, component, data invariants, and verification case. Candidate reconstruction and the full test suite pass.
