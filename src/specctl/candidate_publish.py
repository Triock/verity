"""Submit a verified candidate using a repository-scoped GitHub App token."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .candidate import CURRENT_POINTER, verify_current
from .spec import SpecError


REPOSITORY = "Triock/verity"
ORIGIN = "https://github.com/Triock/verity.git"


def _git(repo: Path, *args: str, env: dict | None = None) -> bytes:
    result = subprocess.run(["git", "-c", "credential.helper=", *args], cwd=repo, env=env, capture_output=True)
    if result.returncode:
        raise SpecError(f"git {args[0]} failed: {result.stderr.decode(errors='replace').strip()}")
    return result.stdout


def _api(base: str, token: str, method: str, path: str, body: dict | None = None):
    data = None if body is None else json.dumps(body, separators=(",", ":")).encode()
    request = urllib.request.Request(
        base + path,
        data=data,
        method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Content-Type": "application/json"} if data is not None else {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise SpecError(f"GitHub API {method} {path} returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise SpecError(f"GitHub API {method} {path} is unavailable") from exc


def _token(path: Path) -> str:
    try:
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise SpecError("installation token file must be owned by this user and mode 600")
        token = path.read_text().strip()
    except OSError as exc:
        raise SpecError(f"cannot read installation token file: {exc}") from exc
    if not token or any(character.isspace() for character in token):
        raise SpecError("installation token file is empty or malformed")
    return token


def _check_tracked(repo: Path, relative: str) -> None:
    path = repo / relative
    try:
        current = path.read_bytes()
    except OSError as exc:
        raise SpecError(f"candidate file is missing: {relative}") from exc
    if current != _git(repo, "show", f"HEAD:{relative}"):
        raise SpecError(f"candidate file is not committed at HEAD: {relative}")


def _pr_body(record: dict, evidence: dict) -> str:
    acceptance = evidence["acceptance"]
    return (
        "## Candidate provenance\n"
        f"- Spec revision: `{record['spec_revision']}`\n"
        f"- Candidate ID: `{record['candidate_id']}`\n"
        f"- Resolved digest: `{record['resolved_sha256']}`\n"
        f"- Generated artifact digest: `{record['artifact']['sha256']}`\n"
        f"- Generator digest: `{record['generator']['sha256']}`\n"
        "\n## Executed evidence\n"
        f"- `{evidence['tests']['command']}`: exit {evidence['tests']['exit_code']}\n"
        f"- Acceptance case `{acceptance['case_id']}`: {'passed' if acceptance['passed'] else 'failed'}\n"
        f"- Submitted input: `{json.dumps(acceptance['input'], sort_keys=True)}`\n"
        f"- Observed response: `{json.dumps(acceptance['observed'], sort_keys=True)}`\n"
        "\nThe catalog was reconstructed byte-for-byte from the pinned inputs. "
        "This candidate is for human review; it is not a release or production promotion. "
        "The spec-model and specctl components remain bootstrap.\n"
    )


def submit_candidate(
    repo: Path,
    token_path: Path,
    branch: str,
    base: str = "main",
    *,
    api_base: str = "https://api.github.com",
    expected_origin: str = ORIGIN,
    api_call=_api,
) -> str:
    """Push a verified branch and create or find its Triock pull request."""
    repo = Path(repo).resolve()
    if base != "main":
        raise SpecError("candidate submissions currently target main only")
    if _git(repo, "branch", "--show-current").decode().strip() != branch or branch == "main":
        raise SpecError("candidate branch does not match the current non-main branch")
    _git(repo, "check-ref-format", "--branch", branch)
    if _git(repo, "remote", "get-url", "origin").decode().strip() != expected_origin:
        raise SpecError("origin does not match the approved Triock repository")
    if _git(repo, "status", "--porcelain").strip():
        raise SpecError("candidate branch must be clean before submission")
    record = verify_current(repo)
    record_relative = f".verity/candidates/{record['candidate_id']}/candidate.json"
    evidence_relative = f".verity/candidates/{record['candidate_id']}/evidence.json"
    for relative in (CURRENT_POINTER, record_relative, evidence_relative, record["artifact"]["path"]):
        _check_tracked(repo, relative)
    evidence = json.loads((repo / evidence_relative).read_text())
    if evidence.get("status") != "passed" or evidence.get("candidate_id") != record["candidate_id"]:
        raise SpecError("candidate evidence does not record a passing evaluation")
    token = _token(Path(token_path))
    scope = api_call(api_base, token, "GET", "/installation/repositories")
    if scope.get("total_count") != 1 or [item.get("full_name") for item in scope.get("repositories", [])] != [REPOSITORY]:
        raise SpecError("GitHub App installation token scope is not exclusively Triock/verity")
    with tempfile.TemporaryDirectory(prefix="verity-app-auth-") as directory:
        token_copy = Path(directory) / "token"
        token_copy.write_text(token)
        token_copy.chmod(0o600)
        askpass = Path(directory) / "askpass"
        askpass.write_text('#!/bin/sh\ncase "$1" in\n  *Username*) printf "x-access-token\\n" ;;\n  *Password*) cat "$VERITY_TOKEN_FILE" ;;\nesac\n')
        askpass.chmod(0o700)
        env = os.environ.copy()
        env.update({"GIT_ASKPASS": str(askpass), "GIT_TERMINAL_PROMPT": "0", "VERITY_TOKEN_FILE": str(token_copy)})
        _git(repo, "push", "origin", f"HEAD:refs/heads/{branch}", env=env)
    query = urllib.parse.urlencode({"head": f"Triock:{branch}", "base": base, "state": "open"})
    pulls = api_call(api_base, token, "GET", f"/repos/{REPOSITORY}/pulls?{query}")
    if not isinstance(pulls, list):
        raise SpecError("GitHub returned an invalid pull-request list")
    for pull in pulls:
        if pull.get("head", {}).get("ref") == branch and pull.get("base", {}).get("ref") == base:
            return pull["html_url"]
    created = api_call(api_base, token, "POST", f"/repos/{REPOSITORY}/pulls", {
        "title": "Generate component catalog from pinned self-spec",
        "head": branch,
        "base": base,
        "body": _pr_body(record, evidence),
    })
    if not isinstance(created, dict) or not isinstance(created.get("html_url"), str):
        raise SpecError("GitHub returned an invalid created pull request")
    return created["html_url"]
