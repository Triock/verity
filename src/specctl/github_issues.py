"""Read and normalize triaged GitHub Issues as untrusted workflow input."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from .candidate_publish import REPOSITORY, _api, _token
from .spec import SpecError


READY_LABEL = "verity:ready"
API_BASE = "https://api.github.com"


def _positive(value: object, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise SpecError(f"GitHub {label} must be a positive integer")
    return value


def _bounded_text(value: object, label: str, limit: int, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise SpecError(f"GitHub {label} must be text")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise SpecError(f"GitHub {label} is not UTF-8 encodable") from exc
    if size > limit:
        raise SpecError(f"GitHub {label} exceeds {limit} bytes")
    return value


def normalize_issue(raw: object, number: int) -> dict:
    """Accept only the declared fields of one ready issue in Triock/verity."""
    number = _positive(number, "issue number")
    if not isinstance(raw, dict):
        raise SpecError("GitHub issue response must be an object")
    if "pull_request" in raw:
        raise SpecError("GitHub pull request is not an issue intake source")
    issue_id = _positive(raw.get("id"), "issue ID")
    if raw.get("number") != number or type(raw.get("number")) is not int:
        raise SpecError("GitHub issue number does not match requested number")
    if raw.get("repository_url") != f"{API_BASE}/repos/{REPOSITORY}":
        raise SpecError("GitHub issue repository is not Triock/verity")
    url = f"https://github.com/{REPOSITORY}/issues/{number}"
    if raw.get("html_url") != url:
        raise SpecError("GitHub issue URL is not the requested Triock/verity issue")
    if raw.get("state") != "open":
        raise SpecError("GitHub issue must be open")
    title = _bounded_text(raw.get("title"), "title", 512)
    body = _bounded_text(raw.get("body") or "", "body", 65536, allow_empty=True)
    updated_at = raw.get("updated_at")
    if not isinstance(updated_at, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", updated_at):
        raise SpecError("GitHub issue updated_at must be a UTC timestamp")
    try:
        parsed = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SpecError("GitHub issue updated_at is invalid") from exc
    if parsed.tzinfo != timezone.utc:
        raise SpecError("GitHub issue updated_at must be UTC")
    labels_raw = raw.get("labels")
    if not isinstance(labels_raw, list):
        raise SpecError("GitHub issue labels must be a list")
    labels = []
    for entry in labels_raw:
        if not isinstance(entry, dict):
            raise SpecError("GitHub issue labels must contain objects")
        labels.append(_bounded_text(entry.get("name"), "labels name", 128))
    if len(labels) != len(set(labels)):
        raise SpecError("GitHub issue labels contain duplicates")
    if READY_LABEL not in labels:
        raise SpecError(f"GitHub issue requires {READY_LABEL} label")
    return {
        "version": 1,
        "source": {
            "provider": "github",
            "repository": REPOSITORY,
            "issue_id": issue_id,
            "number": number,
            "url": url,
            "updated_at": updated_at,
        },
        "title": title,
        "body": body,
        "labels": sorted(labels),
    }


def fetch_issue(number: int, token_path: Path, api_call=_api) -> dict:
    """Fetch one issue with an installation token limited to Triock/verity."""
    number = _positive(number, "issue number")
    token = _token(Path(token_path))
    scope = api_call(API_BASE, token, "GET", "/installation/repositories")
    if not isinstance(scope, dict) or scope.get("total_count") != 1 or [item.get("full_name") for item in scope.get("repositories", [])] != [REPOSITORY]:
        raise SpecError("GitHub App token scope is not exclusively Triock/verity")
    raw = api_call(API_BASE, token, "GET", f"/repos/{REPOSITORY}/issues/{number}")
    return normalize_issue(raw, number)
