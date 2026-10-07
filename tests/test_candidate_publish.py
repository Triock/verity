import tempfile
import os
import subprocess
import sys
import unittest
from pathlib import Path

from specctl.candidate import build_candidate
from specctl.candidate_publish import submit_candidate
from specctl.spec import SpecError
from tests.test_candidate import candidate_repo, git


class FakeGitHub:
    def __init__(self):
        self.scope = ["Triock/verity"]
        self.posts = []
        self.pulls = []

    def request(self, base, token, method, path, body=None):
        if token != "test-installation-token" or base != "https://api.github.test":
            raise AssertionError("wrong API identity")
        if (method, path) == ("GET", "/installation/repositories"):
            return {"total_count": len(self.scope), "repositories": [{"full_name": name} for name in self.scope]}
        if method == "GET" and path.startswith("/repos/Triock/verity/pulls?"):
            return self.pulls
        if (method, path) == ("POST", "/repos/Triock/verity/pulls"):
            self.posts.append(body)
            pr = {"html_url": "https://github.com/Triock/verity/pull/99", "head": {"ref": body["head"]}, "base": {"ref": body["base"]}}
            self.pulls.append(pr)
            return pr
        raise AssertionError(f"unexpected API call: {method} {path}")


class CandidatePublishTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeGitHub()

    def setup_repo(self, directory):
        root = Path(directory)
        repo = root / "repo"
        repo.mkdir()
        repo, revision = candidate_repo(repo)
        git(repo, "branch", "-M", "feat/catalog-candidate")
        build_candidate(repo / "spec" / "solution.json", revision, repo)
        git(repo, "add", ".")
        git(repo, "-c", "user.name=Richard Hillman", "-c", "user.email=triock@gmail.com", "commit", "-qm", "candidate")
        remote = root / "remote.git"
        remote.mkdir()
        git(remote, "init", "--bare", "-q")
        git(repo, "remote", "add", "origin", str(remote))
        token = root / "token"
        token.write_text("test-installation-token")
        token.chmod(0o600)
        return repo, remote, token

    def submit(self, repo, remote, token):
        return submit_candidate(repo, token, "feat/catalog-candidate", api_base="https://api.github.test", expected_origin=str(remote), api_call=self.api.request)

    def test_submits_scoped_branch_and_reuses_existing_pr(self):
        with tempfile.TemporaryDirectory() as directory:
            repo, remote, token = self.setup_repo(directory)
            self.assertEqual(self.submit(repo, remote, token), "https://github.com/Triock/verity/pull/99")
            self.assertEqual(git(remote, "rev-parse", "refs/heads/feat/catalog-candidate"), git(repo, "rev-parse", "HEAD"))
            self.assertEqual(self.submit(repo, remote, token), "https://github.com/Triock/verity/pull/99")
            self.assertEqual(len(self.api.posts), 1)
            self.assertIn("Candidate ID", self.api.posts[0]["body"])

    def test_rejects_wrong_app_repository_scope_before_push(self):
        with tempfile.TemporaryDirectory() as directory:
            repo, remote, token = self.setup_repo(directory)
            self.api.scope = ["RichardHillman-Aderant/verity"]
            with self.assertRaisesRegex(SpecError, "scope"):
                self.submit(repo, remote, token)
            self.assertEqual(len(self.api.posts), 0)
            with self.assertRaises(Exception):
                git(remote, "show-ref", "--verify", "-q", "refs/heads/feat/catalog-candidate")

    def test_rejects_push_url_to_other_account(self):
        with tempfile.TemporaryDirectory() as directory:
            repo, remote, token = self.setup_repo(directory)
            git(repo, "remote", "set-url", "--push", "origin", "https://github.com/RichardHillman-Aderant/verity.git")
            with self.assertRaisesRegex(SpecError, "push URL"):
                self.submit(repo, remote, token)
            self.assertEqual(len(self.api.posts), 0)

    def test_rejects_dirty_branch_and_missing_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            repo, remote, token = self.setup_repo(directory)
            (repo / "dirty.txt").write_text("uncommitted")
            with self.assertRaisesRegex(SpecError, "clean"):
                self.submit(repo, remote, token)
            (repo / "dirty.txt").unlink()
            evidence = next((repo / ".verity" / "candidates").glob("*/evidence.json"))
            evidence.unlink()
            git(repo, "add", "-u")
            git(repo, "-c", "user.name=Richard Hillman", "-c", "user.email=triock@gmail.com", "commit", "-qm", "remove evidence")
            with self.assertRaisesRegex(SpecError, "evidence"):
                self.submit(repo, remote, token)

    def test_cli_submit_reports_missing_token_without_remote_write(self):
        with tempfile.TemporaryDirectory() as directory:
            repo, remote, _ = self.setup_repo(directory)
            git(repo, "remote", "set-url", "origin", "https://github.com/Triock/verity.git")
            env = os.environ.copy()
            env["PYTHONPATH"] = str(repo / "src")
            result = subprocess.run(
                [sys.executable, "-m", "specctl", "candidate", "submit", "--branch", "feat/catalog-candidate", "--token-file", str(repo / "missing-token")],
                cwd=repo, env=env, text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("token", result.stderr)
            with self.assertRaises(Exception):
                git(remote, "show-ref", "--verify", "-q", "refs/heads/feat/catalog-candidate")


if __name__ == "__main__":
    unittest.main()
