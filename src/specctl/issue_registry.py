"""Record immutable, Git-trackable snapshots of observed issue inputs."""

from __future__ import annotations

import fcntl
import hashlib
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

from .spec import SpecError, decode_json
from .v2_resolve import canonical_bytes


def _directory(path: Path) -> None:
    if path.is_symlink():
        raise SpecError(f"issue registry path is a symlink: {path}")
    try:
        path.mkdir(exist_ok=True)
    except OSError as exc:
        raise SpecError(f"cannot create issue registry directory {path}: {exc}") from exc
    if path.is_symlink() or not path.is_dir():
        raise SpecError(f"issue registry path is not a safe directory: {path}")


def _read(path: Path) -> dict:
    if path.is_symlink():
        raise SpecError(f"issue registry path is a symlink: {path}")
    try:
        value = decode_json(path.read_bytes(), str(path))
    except OSError as exc:
        raise SpecError(f"cannot read issue registry file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SpecError(f"issue registry file is not an object: {path}")
    return value


def _write(path: Path, content: bytes) -> None:
    if path.is_symlink():
        raise SpecError(f"issue registry path is a symlink: {path}")
    staged = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            staged = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staged, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        raise SpecError(f"cannot write issue registry file {path}: {exc}") from exc
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)


def record_issue(repo: Path, snapshot: dict) -> dict:
    """Append one validated issue revision, then publish its local pointer."""
    if not isinstance(snapshot, dict) or set(snapshot) != {"version", "source", "title", "body", "labels"} or snapshot["version"] != 1:
        raise SpecError("issue snapshot has an invalid schema")
    source = snapshot["source"]
    if not isinstance(source, dict) or set(source) != {"provider", "repository", "issue_id", "number", "url", "updated_at"}:
        raise SpecError("issue source has an invalid schema")
    number = source["number"]
    if source["provider"] != "github" or source["repository"] != "Triock/verity" or type(number) is not int or number <= 0:
        raise SpecError("issue source must identify a Triock/verity GitHub issue")
    if type(source["issue_id"]) is not int or source["issue_id"] <= 0 or source["url"] != f"https://github.com/Triock/verity/issues/{number}":
        raise SpecError("issue source ID or URL is invalid")
    updated_at = source["updated_at"]
    if not isinstance(updated_at, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", updated_at):
        raise SpecError("issue source updated_at is invalid")
    try:
        datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        body = canonical_bytes(snapshot)
    except (ValueError, TypeError, UnicodeEncodeError) as exc:
        raise SpecError("issue snapshot contains invalid values") from exc
    digest = hashlib.sha256(body).hexdigest()
    repo = Path(repo).resolve()
    issue_dir = repo / ".verity" / "issues" / "github" / str(number)
    path = repo
    for part in (".verity", "issues", "github", str(number)):
        path = path / part
        _directory(path)
    snapshots = issue_dir / "snapshots"
    _directory(snapshots)
    snapshot_path = snapshots / f"{digest}.json"
    pointer_path = issue_dir / "current.json"
    result = {
        "source": f"github:Triock/verity#{number}",
        "digest": digest,
        "snapshot_path": snapshot_path.relative_to(repo).as_posix(),
        "current_path": pointer_path.relative_to(repo).as_posix(),
        "committed": False,
    }
    try:
        lock_fd = os.open(issue_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        if snapshot_path.is_symlink() or pointer_path.is_symlink():
            raise SpecError("issue registry path is a symlink")
        content = body + b"\n"
        if snapshot_path.exists() and snapshot_path.read_bytes() != content:
            raise SpecError("existing issue snapshot conflicts with its digest")
        if pointer_path.exists():
            pointer = _read(pointer_path)
            old_digest = pointer.get("digest")
            if set(pointer) != {"version", "digest", "updated_at"} or pointer["version"] != 1 or not isinstance(old_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", old_digest):
                raise SpecError("current issue pointer is invalid")
            old_path = snapshots / f"{old_digest}.json"
            old = _read(old_path)
            old_body = canonical_bytes(old)
            if hashlib.sha256(old_body).hexdigest() != old_digest or old_path.read_bytes() != old_body + b"\n":
                raise SpecError("current issue snapshot digest does not match its bytes")
            old_source = old.get("source")
            if not isinstance(old_source, dict) or old_source.get("issue_id") != source["issue_id"] or old_source.get("number") != number or pointer["updated_at"] != old_source.get("updated_at"):
                raise SpecError("current issue pointer does not match source identity")
            if updated_at < pointer["updated_at"]:
                raise SpecError("older issue update cannot replace current snapshot")
            if updated_at == pointer["updated_at"] and digest != old_digest:
                raise SpecError("same update time has conflicting issue content")
            if digest == old_digest:
                return result
        if not snapshot_path.exists():
            _write(snapshot_path, content)
        _write(pointer_path, canonical_bytes({"version": 1, "digest": digest, "updated_at": updated_at}) + b"\n")
        return result
    except OSError as exc:
        raise SpecError(f"cannot lock issue registry: {exc}") from exc
    finally:
        if "lock_fd" in locals():
            os.close(lock_fd)
