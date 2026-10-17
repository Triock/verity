"""Persist one validated GitHub Issue as a resumable Git workflow."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .candidate_publish import ORIGIN, REPOSITORY, _api, _git, _token
from .github_issues import READY_LABEL
from .issue_registry import _write, record_issue
from .spec import SpecError, decode_json
from .v2_resolve import canonical_bytes


AUTHOR = "Richard Hillman"
EMAIL = "triock@gmail.com"
API_BASE = "https://api.github.com"


def _text(repo: Path, *args: str, env: dict | None = None) -> str:
    return _git(repo, *args, env=env).decode().strip()


def _ref_exists(repo: Path, ref: str) -> bool:
    return subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", ref], cwd=repo, capture_output=True
    ).returncode == 0


def _changed_paths(repo: Path) -> set[str]:
    paths = set()
    for args in (
        ("diff", "--name-only", "-z"),
        ("diff", "--cached", "--name-only", "-z"),
        ("ls-files", "--others", "--exclude-standard", "-z"),
    ):
        paths.update(path.decode() for path in _git(repo, *args).split(b"\0") if path)
    return paths


def _remote_refs(repo: Path, env: dict, branch: str) -> dict[str, str]:
    output = _text(
        repo, "ls-remote", "--heads", "origin", "refs/heads/main", f"refs/heads/{branch}", env=env
    )
    refs = {}
    for line in output.splitlines():
        sha, ref = line.split("\t", 1)
        refs[ref] = sha
    if "refs/heads/main" not in refs:
        raise SpecError("approved remote has no main branch")
    return refs


@contextmanager
def _git_auth(token_path: Path):
    with tempfile.TemporaryDirectory(prefix="verity-issue-auth-") as directory:
        askpass = Path(directory) / "askpass"
        askpass.write_text(
            '#!/bin/sh\ncase "$1" in\n'
            '  *Username*) printf "x-access-token\\n" ;;\n'
            '  *Password*) cat "$VERITY_TOKEN_FILE" ;;\n'
            'esac\n'
        )
        askpass.chmod(0o700)
        env = os.environ.copy()
        env.update({
            "GIT_ASKPASS": str(askpass),
            "GIT_TERMINAL_PROMPT": "0",
            "VERITY_TOKEN_FILE": str(token_path.resolve()),
        })
        yield env


def _workflow_path(repo: Path, number: int) -> Path:
    return repo / ".verity" / "issues" / "github" / str(number) / "workflow.json"


def _check_workflow(path: Path, source: dict, branch: str, *, required: bool) -> dict | None:
    if path.is_symlink():
        raise SpecError("issue workflow path is a symlink")
    if not path.exists():
        if required:
            raise SpecError("existing issue branch has no workflow record")
        return None
    try:
        workflow = decode_json(path.read_bytes(), str(path))
    except OSError as exc:
        raise SpecError(f"cannot read issue workflow: {exc}") from exc
    identity = {key: source[key] for key in ("provider", "repository", "issue_id", "number")}
    if (
        not isinstance(workflow, dict)
        or set(workflow) != {"version", "source", "branch", "digest", "stage", "base_revision"}
        or workflow["version"] != 1
        or workflow["source"] != identity
        or workflow["branch"] != branch
        or workflow["stage"] != "awaiting-spec"
        or not isinstance(workflow["digest"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", workflow["digest"])
        or not isinstance(workflow["base_revision"], str)
        or not re.fullmatch(r"[0-9a-f]{40}", workflow["base_revision"])
    ):
        raise SpecError("existing issue workflow conflicts with source or branch")
    return workflow


def _committed_workflow(repo: Path, path: Path, source: dict, branch: str, *, required: bool) -> dict | None:
    relative = path.relative_to(repo).as_posix()
    exists = subprocess.run(["git", "cat-file", "-e", f"HEAD:{relative}"], cwd=repo, capture_output=True).returncode == 0
    if not exists:
        if required:
            raise SpecError("existing remote issue branch has no committed workflow record")
        return None
    with tempfile.TemporaryDirectory(prefix="verity-workflow-read-") as directory:
        stored = Path(directory) / "workflow.json"
        stored.write_bytes(_git(repo, "show", f"HEAD:{relative}"))
        workflow = _check_workflow(stored, source, branch, required=True)
    issue_prefix = f".verity/issues/github/{source['number']}/"
    pointer = decode_json(_git(repo, "show", f"HEAD:{issue_prefix}current.json"), "committed issue pointer")
    if not isinstance(pointer, dict) or pointer.get("digest") != workflow["digest"]:
        raise SpecError("committed workflow digest does not match issue pointer")
    digest = workflow["digest"]
    raw = _git(repo, "show", f"HEAD:{issue_prefix}snapshots/{digest}.json")
    saved = decode_json(raw, "committed issue snapshot")
    if raw != canonical_bytes(saved) + b"\n" or hashlib.sha256(canonical_bytes(saved)).hexdigest() != digest:
        raise SpecError("committed workflow digest does not match issue snapshot")
    saved_source = saved.get("source") if isinstance(saved, dict) else None
    if not isinstance(saved_source, dict) or any(saved_source.get(key) != source[key] for key in ("provider", "repository", "issue_id", "number")):
        raise SpecError("committed workflow snapshot source conflicts with issue")
    return workflow


def _check_history(repo: Path, base: str, source: dict) -> None:
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", base, "HEAD"], cwd=repo, capture_output=True)
    if ancestor.returncode:
        raise SpecError("issue workflow base revision is not an ancestor")
    commits = _text(repo, "rev-list", "--reverse", f"{base}..HEAD").splitlines()
    number = source["number"]
    prefix = f".verity/issues/github/{number}/"
    allowed_fixed = {prefix + "current.json", prefix + "workflow.json"}
    for commit in commits:
        parents, author, committer, message = _text(repo, "show", "-s", "--format=%P%n%an <%ae>%n%cn <%ce>%n%B", commit).split("\n", 3)
        changes = [line.split("\t", 1) for line in _text(repo, "diff-tree", "--no-commit-id", "--name-status", "-r", commit).splitlines()]
        safe_paths = bool(changes)
        for entry in changes:
            if len(entry) != 2:
                safe_paths = False
                break
            status, path = entry
            snapshot_match = re.fullmatch(re.escape(prefix) + r"snapshots/([0-9a-f]{64})\.json", path)
            if path in allowed_fixed:
                safe_paths &= status in ("A", "M")
            elif snapshot_match and status == "A":
                raw = _git(repo, "show", f"{commit}:{path}")
                saved = decode_json(raw, f"committed {path}")
                saved_source = saved.get("source") if isinstance(saved, dict) else None
                safe_paths &= (
                    raw == canonical_bytes(saved) + b"\n"
                    and hashlib.sha256(canonical_bytes(saved)).hexdigest() == snapshot_match.group(1)
                    and isinstance(saved_source, dict)
                    and all(saved_source.get(key) == source[key] for key in ("provider", "repository", "issue_id", "number"))
                )
            else:
                safe_paths = False
            if not safe_paths:
                break
        if (
            len(parents.split()) != 1
            or author != f"{AUTHOR} <{EMAIL}>"
            or committer != f"{AUTHOR} <{EMAIL}>"
            or message.strip() != f"data: record issue {number} workflow input"
            or not safe_paths
        ):
            raise SpecError("issue branch contains an unrelated commit")


def start_issue(
    repo: Path,
    snapshot: dict,
    token_path: Path,
    *,
    expected_origin: str = ORIGIN,
    api_call=_api,
) -> dict:
    """Commit and confirm one issue revision on its fixed remote branch."""
    repo = Path(repo).resolve()
    source = snapshot.get("source") if isinstance(snapshot, dict) else None
    if not isinstance(source, dict):
        raise SpecError("issue snapshot has no source")
    number = source.get("number")
    if (
        type(number) is not int or number <= 0
        or source.get("provider") != "github"
        or source.get("repository") != REPOSITORY
        or not isinstance(snapshot.get("labels"), list)
        or READY_LABEL not in snapshot["labels"]
    ):
        raise SpecError("issue workflow requires a ready Triock/verity issue")
    branch = f"verity/issue-{number}"
    if _text(repo, "remote", "get-url", "--all", "origin").splitlines() != [expected_origin]:
        raise SpecError("origin does not match the approved Triock repository")
    if _text(repo, "remote", "get-url", "--all", "--push", "origin").splitlines() != [expected_origin]:
        raise SpecError("origin push URL does not match the approved Triock repository")
    if _text(repo, "config", "--local", "--get", "user.name") != AUTHOR or _text(repo, "config", "--local", "--get", "user.email") != EMAIL:
        raise SpecError("Git author and committer must be Richard Hillman <triock@gmail.com>")
    current_branch = _text(repo, "branch", "--show-current")
    if current_branch not in ("main", branch):
        raise SpecError("issue start requires main or its fixed issue branch")
    issue_prefix = f".verity/issues/github/{number}/"
    dirty = _changed_paths(repo)
    if current_branch == "main" and dirty:
        raise SpecError("issue start requires clean main")
    if current_branch == branch and any(not path.startswith(issue_prefix) for path in dirty):
        raise SpecError("issue branch contains unrelated changes")

    token_path = Path(token_path)
    token = _token(token_path)
    scope = api_call(API_BASE, token, "GET", "/installation/repositories")
    repositories = scope.get("repositories") if isinstance(scope, dict) else None
    if (
        not isinstance(scope, dict) or scope.get("total_count") != 1
        or not isinstance(repositories, list) or len(repositories) != 1
        or not isinstance(repositories[0], dict)
        or repositories[0].get("full_name") != REPOSITORY
    ):
        raise SpecError("GitHub App token scope is not exclusively Triock/verity")

    with _git_auth(token_path) as env:
        refs = _remote_refs(repo, env, branch)
        remote_branch = refs.get(f"refs/heads/{branch}")
        if _text(repo, "rev-parse", "refs/heads/main") != refs["refs/heads/main"]:
            raise SpecError("local main differs from approved remote main")
        if remote_branch:
            _git(repo, "fetch", "origin", f"refs/heads/{branch}:refs/remotes/origin/{branch}", env=env)
        if current_branch == "main":
            local_branch = _ref_exists(repo, f"refs/heads/{branch}")
            if local_branch:
                _git(repo, "switch", branch)
            elif remote_branch:
                _git(repo, "switch", "-c", branch, f"refs/remotes/origin/{branch}")
            else:
                _git(repo, "switch", "-c", branch)

        workflow_path = _workflow_path(repo, number)
        if remote_branch:
            ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", remote_branch, "HEAD"], cwd=repo, capture_output=True)
            if ancestor.returncode:
                raise SpecError("local issue branch does not include current remote branch")
        committed = _committed_workflow(repo, workflow_path, source, branch, required=bool(remote_branch))
        pending = _check_workflow(workflow_path, source, branch, required=bool(remote_branch))
        base_revision = _text(repo, "merge-base", "HEAD", "main")
        for existing in (committed, pending):
            if existing is not None and existing["base_revision"] != base_revision:
                raise SpecError("issue workflow base revision conflicts with main ancestry")
        _check_history(repo, base_revision, source)
        recorded = record_issue(repo, snapshot)
        workflow = {
            "version": 1,
            "source": {key: source[key] for key in ("provider", "repository", "issue_id", "number")},
            "branch": branch,
            "base_revision": base_revision,
            "digest": recorded["digest"],
            "stage": "awaiting-spec",
        }
        content = canonical_bytes(workflow) + b"\n"
        if not workflow_path.exists() or workflow_path.read_bytes() != content:
            _write(workflow_path, content)
        allowed = {
            recorded["snapshot_path"], recorded["current_path"],
            workflow_path.relative_to(repo).as_posix(),
        }
        if _changed_paths(repo) - allowed:
            raise SpecError("unexpected pending issue path")
        _git(repo, "add", "--", *sorted(allowed))
        staged = _text(repo, "diff", "--cached", "--name-only")
        created_commit = bool(staged)
        if created_commit:
            commit_env = env.copy()
            commit_env.update({
                "GIT_AUTHOR_NAME": AUTHOR, "GIT_AUTHOR_EMAIL": EMAIL,
                "GIT_COMMITTER_NAME": AUTHOR, "GIT_COMMITTER_EMAIL": EMAIL,
            })
            _git(repo, "commit", "-m", f"data: record issue {number} workflow input", env=commit_env)
        _check_history(repo, base_revision, source)
        try:
            committed_workflow = _committed_workflow(repo, workflow_path, source, branch, required=True)
            expected_pointer = canonical_bytes({
                "version": 1, "digest": recorded["digest"], "updated_at": source["updated_at"],
            }) + b"\n"
            if (
                committed_workflow != workflow
                or _git(repo, "show", f"HEAD:{workflow_path.relative_to(repo).as_posix()}") != content
                or _git(repo, "show", f"HEAD:{recorded['current_path']}") != expected_pointer
                or _git(repo, "show", f"HEAD:{recorded['snapshot_path']}") != canonical_bytes(snapshot) + b"\n"
            ):
                raise SpecError("committed workflow differs from intended state")
        except SpecError as exc:
            raise SpecError(f"committed workflow validation failed: {exc}") from exc
        commit = _text(repo, "rev-parse", "HEAD")
        try:
            _git(
                repo, "-c", "push.followTags=false", "push",
                f"--force-with-lease=refs/heads/{branch}:{remote_branch or ''}",
                "origin", f"HEAD:refs/heads/{branch}", env=env,
            )
        except SpecError as exc:
            raise SpecError(f"git push failed: {exc}") from exc
        confirmed = _remote_refs(repo, env, branch).get(f"refs/heads/{branch}")
        if confirmed != commit:
            raise SpecError("remote issue branch does not match committed workflow revision")
        return {
            "source": recorded["source"],
            "digest": recorded["digest"],
            "branch": branch,
            "commit": commit,
            "stage": "awaiting-spec",
            "durable": True,
            "created_commit": created_commit,
        }
