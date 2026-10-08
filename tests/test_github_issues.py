import copy
import tempfile
import unittest
from pathlib import Path

from specctl.github_issues import fetch_issue, normalize_issue
from specctl.spec import SpecError


READY_ISSUE = {
    "id": 81,
    "number": 7,
    "state": "open",
    "title": "Add a recovery check",
    "body": "Restore the workflow record after restart.",
    "html_url": "https://github.com/Triock/verity/issues/7",
    "repository_url": "https://api.github.com/repos/Triock/verity",
    "updated_at": "2026-10-07T13:00:00Z",
    "labels": [{"name": "verity:ready"}, {"name": "data-integrity"}],
}


class GitHubIssueTests(unittest.TestCase):
    def test_normalizes_only_declared_fields_in_stable_order(self):
        raw = copy.deepcopy(READY_ISSUE)
        raw["untrusted_extra"] = {"command": "rm -rf /"}
        result = normalize_issue(raw, 7)
        self.assertEqual(result, {
            "version": 1,
            "source": {
                "provider": "github", "repository": "Triock/verity", "issue_id": 81,
                "number": 7, "url": "https://github.com/Triock/verity/issues/7",
                "updated_at": "2026-10-07T13:00:00Z",
            },
            "title": "Add a recovery check",
            "body": "Restore the workflow record after restart.",
            "labels": ["data-integrity", "verity:ready"],
        })

    def test_rejects_untriaged_closed_and_pull_request_records(self):
        for changed, expected in (
            ({"labels": []}, "verity:ready"),
            ({"state": "closed"}, "open"),
            ({"pull_request": {"url": "https://api.github.com/repos/Triock/verity/pulls/7"}}, "pull request"),
        ):
            with self.subTest(changed=changed):
                raw = copy.deepcopy(READY_ISSUE)
                raw.update(changed)
                with self.assertRaisesRegex(SpecError, expected):
                    normalize_issue(raw, 7)

    def test_rejects_wrong_identity_bad_timestamp_and_oversized_text(self):
        for changed, expected in (
            ({"number": 8}, "number"),
            ({"id": True}, "issue ID"),
            ({"html_url": "https://github.com/RichardHillman-Aderant/verity/issues/7"}, "URL"),
            ({"repository_url": "https://api.github.com/repos/RichardHillman-Aderant/verity"}, "repository"),
            ({"updated_at": "2026-99-07T13:00:00Z"}, "updated_at"),
            ({"title": "x" * 513}, "title"),
            ({"body": "x" * 65537}, "body"),
            ({"body": 0}, "body"),
            ({"labels": [{"name": "verity:ready"}, {"name": "verity:ready"}]}, "labels"),
        ):
            with self.subTest(changed=list(changed)):
                raw = copy.deepcopy(READY_ISSUE)
                raw.update(changed)
                with self.assertRaisesRegex(SpecError, expected):
                    normalize_issue(raw, 7)

    def test_fetch_checks_repository_scope_before_issue_read(self):
        with tempfile.TemporaryDirectory() as directory:
            token = Path(directory) / "token"
            token.write_text("short-lived-token\n")
            token.chmod(0o600)
            paths = []

            def api(base, credential, method, path):
                paths.append(path)
                if path == "/installation/repositories":
                    return {"total_count": 1, "repositories": [{"full_name": "Triock/verity"}]}
                if path == "/repos/Triock/verity/issues/7":
                    return copy.deepcopy(READY_ISSUE)
                raise AssertionError(path)

            self.assertEqual(fetch_issue(7, token, api_call=api)["source"]["issue_id"], 81)
            self.assertEqual(paths, ["/installation/repositories", "/repos/Triock/verity/issues/7"])

            def wrong_scope(base, credential, method, path):
                return {"total_count": 1, "repositories": [{"full_name": "RichardHillman-Aderant/verity"}]}

            with self.assertRaisesRegex(SpecError, "scope"):
                fetch_issue(7, token, api_call=wrong_scope)

            def malformed_scope(base, credential, method, path):
                return {"total_count": 1, "repositories": [None]}

            with self.assertRaisesRegex(SpecError, "scope"):
                fetch_issue(7, token, api_call=malformed_scope)


if __name__ == "__main__":
    unittest.main()
