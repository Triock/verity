import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from specctl import issue_workflow
from specctl.issue_workflow import start_issue
from specctl.issue_registry import record_issue
from specctl.spec import SpecError
from tests.test_issue_registry import snapshot


def git(repo, *args):
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


class IssueWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.remote = root / "remote.git"
        self.repo = root / "repo"
        subprocess.run(["git", "init", "--bare", "-q", str(self.remote)], check=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.repo)], check=True)
        git(self.repo, "config", "user.name", "Richard Hillman")
        git(self.repo, "config", "user.email", "triock@gmail.com")
        git(self.repo, "remote", "add", "origin", str(self.remote))
        (self.repo / "README.md").write_text("test repository\n")
        git(self.repo, "add", "README.md")
        git(self.repo, "commit", "-qm", "seed")
        git(self.repo, "push", "-q", "-u", "origin", "main")
        git(self.remote, "symbolic-ref", "HEAD", "refs/heads/main")
        self.token = root / "token"
        self.token.write_text("sample-installation-token")
        self.token.chmod(0o600)

    def api(self, base, token, method, path):
        self.assertEqual(token, "sample-installation-token")
        self.assertEqual((method, path), ("GET", "/installation/repositories"))
        return {"total_count": 1, "repositories": [{"full_name": "Triock/verity"}]}

    def start(self, repo=None, issue=None):
        return start_issue(
            repo or self.repo, issue or snapshot(), self.token,
            expected_origin=str(self.remote), api_call=self.api,
        )

    def test_first_start_persists_exact_branch_and_replay_is_idempotent(self):
        first = self.start()
        self.assertTrue(first["durable"])
        self.assertTrue(first["created_commit"])
        self.assertEqual(first["stage"], "awaiting-spec")
        self.assertEqual(first["branch"], "verity/issue-7")
        self.assertEqual(first["commit"], git(self.repo, "rev-parse", "HEAD"))
        self.assertEqual(first["commit"], git(self.remote, "rev-parse", "refs/heads/verity/issue-7"))
        self.assertEqual(git(self.repo, "show", "-s", "--format=%an <%ae>%n%cn <%ce>"), "Richard Hillman <triock@gmail.com>\nRichard Hillman <triock@gmail.com>")
        workflow = json.loads((self.repo / ".verity/issues/github/7/workflow.json").read_text())
        self.assertEqual(workflow["digest"], first["digest"])
        self.assertEqual(workflow["source"]["issue_id"], snapshot()["source"]["issue_id"])
        second = self.start()
        self.assertFalse(second["created_commit"])
        self.assertEqual(second["commit"], first["commit"])
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")

    def test_newer_issue_revision_advances_branch_and_old_revision_is_rejected(self):
        first = self.start()
        newer = copy.deepcopy(snapshot())
        newer["source"]["updated_at"] = "2026-10-12T00:00:00Z"
        newer["body"] = "New evidence"
        second = self.start(issue=newer)
        self.assertNotEqual(first["commit"], second["commit"])
        self.assertEqual(second["commit"], git(self.remote, "rev-parse", "refs/heads/verity/issue-7"))
        with self.assertRaisesRegex(SpecError, "older issue update"):
            self.start()
        self.assertEqual(second["commit"], git(self.remote, "rev-parse", "refs/heads/verity/issue-7"))

    def test_failed_push_is_not_durable_and_retry_resumes_local_commit(self):
        hook = self.remote / "hooks/pre-receive"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o700)
        with self.assertRaisesRegex(SpecError, "git push failed"):
            self.start()
        local_commit = git(self.repo, "rev-parse", "HEAD")
        self.assertEqual(git(self.repo, "branch", "--show-current"), "verity/issue-7")
        self.assertNotIn("refs/heads/verity/issue-7", git(self.remote, "show-ref"))
        hook.unlink()
        resumed = self.start()
        self.assertFalse(resumed["created_commit"])
        self.assertEqual(resumed["commit"], local_commit)
        self.assertTrue(resumed["durable"])

    def test_retry_after_snapshot_write_before_commit(self):
        git(self.repo, "switch", "-q", "-c", "verity/issue-7")
        recorded = record_issue(self.repo, snapshot())
        self.assertTrue((self.repo / recorded["current_path"]).exists())
        resumed = self.start()
        self.assertTrue(resumed["created_commit"])
        self.assertTrue(resumed["durable"])
        self.assertEqual(resumed["commit"], git(self.remote, "rev-parse", "refs/heads/verity/issue-7"))

    def test_clean_clone_resumes_remote_branch(self):
        first = self.start()
        clone = Path(self.temp.name) / "clone"
        subprocess.run(["git", "clone", "-q", str(self.remote), str(clone)], check=True)
        git(clone, "config", "user.name", "Richard Hillman")
        git(clone, "config", "user.email", "triock@gmail.com")
        resumed = self.start(repo=clone)
        self.assertEqual(resumed["commit"], first["commit"])
        self.assertFalse(resumed["created_commit"])
        self.assertEqual(git(clone, "branch", "--show-current"), "verity/issue-7")

    def test_rejects_dirty_main_and_wrong_identity_before_branch_change(self):
        (self.repo / "unrelated.txt").write_text("unsaved")
        with self.assertRaisesRegex(SpecError, "clean main"):
            self.start()
        self.assertEqual(git(self.repo, "branch", "--show-current"), "main")
        (self.repo / "unrelated.txt").unlink()
        git(self.repo, "config", "user.email", "wrong@example.com")
        with self.assertRaisesRegex(SpecError, "Richard Hillman"):
            self.start()
        self.assertEqual(git(self.repo, "branch", "--show-current"), "main")

    def test_rejects_wrong_origin_and_token_scope(self):
        with self.assertRaisesRegex(SpecError, "approved Triock repository"):
            start_issue(self.repo, snapshot(), self.token, api_call=self.api)
        def wrong_scope(base, token, method, path):
            return {"total_count": 1, "repositories": [{"full_name": "RichardHillman-Aderant/verity"}]}
        with self.assertRaisesRegex(SpecError, "token scope"):
            start_issue(self.repo, snapshot(), self.token, expected_origin=str(self.remote), api_call=wrong_scope)
        self.assertEqual(git(self.repo, "branch", "--show-current"), "main")

    def test_rejects_extra_staged_issue_file_without_advancing_remote(self):
        first = self.start()
        extra = self.repo / ".verity/issues/github/7/extra.txt"
        extra.write_text("not controller state")
        git(self.repo, "add", "--", ".verity/issues/github/7/extra.txt")
        with self.assertRaisesRegex(SpecError, "unexpected pending issue path"):
            self.start()
        self.assertEqual(git(self.remote, "rev-parse", "refs/heads/verity/issue-7"), first["commit"])

    def test_rejects_unrelated_committed_work_before_push(self):
        first = self.start()
        (self.repo / "unrelated.txt").write_text("unrelated change")
        git(self.repo, "add", "unrelated.txt")
        git(self.repo, "commit", "-qm", "unrelated commit")
        with self.assertRaisesRegex(SpecError, "unrelated commit"):
            self.start()
        self.assertEqual(git(self.remote, "rev-parse", "refs/heads/verity/issue-7"), first["commit"])

    def test_rejects_conflicting_committed_workflow_digest(self):
        first = self.start()
        path = self.repo / ".verity/issues/github/7/workflow.json"
        workflow = json.loads(path.read_text())
        workflow["digest"] = "0" * 64
        path.write_text(json.dumps(workflow, sort_keys=True) + "\n")
        git(self.repo, "add", ".verity/issues/github/7/workflow.json")
        git(self.repo, "commit", "-qm", "data: record issue 7 workflow input")
        git(self.repo, "push", "-q", "origin", "HEAD:refs/heads/verity/issue-7")
        corrupted = git(self.remote, "rev-parse", "refs/heads/verity/issue-7")
        self.assertNotEqual(corrupted, first["commit"])
        with self.assertRaisesRegex(SpecError, "workflow digest"):
            self.start()
        self.assertEqual(git(self.remote, "rev-parse", "refs/heads/verity/issue-7"), corrupted)

    def test_rejects_modified_historical_snapshot(self):
        first = self.start()
        newer = copy.deepcopy(snapshot())
        newer["source"]["updated_at"] = "2026-10-12T00:00:00Z"
        newer["body"] = "New evidence"
        self.start(issue=newer)
        old_path = self.repo / f".verity/issues/github/7/snapshots/{first['digest']}.json"
        old_path.write_text("{}\n")
        git(self.repo, "add", "--", str(old_path.relative_to(self.repo)))
        git(self.repo, "commit", "-qm", "data: record issue 7 workflow input")
        git(self.repo, "push", "-q", "origin", "HEAD:refs/heads/verity/issue-7")
        corrupted = git(self.remote, "rev-parse", "refs/heads/verity/issue-7")
        with self.assertRaisesRegex(SpecError, "unrelated commit"):
            self.start(issue=newer)
        self.assertEqual(git(self.remote, "rev-parse", "refs/heads/verity/issue-7"), corrupted)

    def test_pending_workflow_cannot_hide_an_unrelated_commit_in_its_base(self):
        git(self.repo, "switch", "-q", "-c", "verity/issue-7")
        (self.repo / "unrelated.txt").write_text("unrelated change")
        git(self.repo, "add", "unrelated.txt")
        git(self.repo, "commit", "-qm", "unrelated commit")
        unrelated = git(self.repo, "rev-parse", "HEAD")
        path = self.repo / ".verity/issues/github/7/workflow.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({
            "version": 1,
            "source": {key: snapshot()["source"][key] for key in ("provider", "repository", "issue_id", "number")},
            "branch": "verity/issue-7", "base_revision": unrelated,
            "digest": "0" * 64, "stage": "awaiting-spec",
        }) + "\n")
        with self.assertRaisesRegex(SpecError, "base revision"):
            self.start()
        self.assertNotIn("refs/heads/verity/issue-7", git(self.remote, "show-ref"))

    def test_issue_branch_rejects_local_main_moved_past_unrelated_commit(self):
        git(self.repo, "switch", "-q", "-c", "verity/issue-7")
        (self.repo / "unrelated.txt").write_text("unrelated change")
        git(self.repo, "add", "unrelated.txt")
        git(self.repo, "commit", "-qm", "unrelated commit")
        git(self.repo, "branch", "-f", "main", "HEAD")
        with self.assertRaisesRegex(SpecError, "local main differs"):
            self.start()
        self.assertNotIn("refs/heads/verity/issue-7", git(self.remote, "show-ref"))

    def test_new_remote_branch_created_during_start_is_not_overwritten(self):
        original = issue_workflow._remote_refs
        calls = 0

        def racing_refs(repo, env, branch):
            nonlocal calls
            refs = original(repo, env, branch)
            calls += 1
            if calls == 1:
                main = git(self.remote, "rev-parse", "refs/heads/main")
                git(self.remote, "update-ref", "refs/heads/verity/issue-7", main)
            return refs

        with patch("specctl.issue_workflow._remote_refs", side_effect=racing_refs):
            with self.assertRaisesRegex(SpecError, "git push failed"):
                self.start()
        self.assertEqual(git(self.remote, "rev-parse", "refs/heads/verity/issue-7"), git(self.remote, "rev-parse", "refs/heads/main"))

    def test_rejects_git_filter_that_changes_staged_workflow(self):
        (self.repo / ".gitattributes").write_text("**/workflow.json filter=rewrite\n")
        git(self.repo, "config", "filter.rewrite.clean", "sed 's/awaiting-spec/altered-stage/g'")
        git(self.repo, "config", "filter.rewrite.required", "true")
        git(self.repo, "add", ".gitattributes")
        git(self.repo, "commit", "-qm", "add attributes")
        git(self.repo, "push", "-q", "origin", "main")
        with self.assertRaisesRegex(SpecError, "committed workflow"):
            self.start()
        self.assertNotIn("refs/heads/verity/issue-7", git(self.remote, "show-ref"))

    def test_does_not_publish_unrelated_annotated_tags(self):
        git(self.repo, "tag", "-a", "local-only", "-m", "unrelated local tag")
        git(self.repo, "config", "push.followTags", "true")
        self.start()
        self.assertEqual(git(self.remote, "tag", "--list"), "")


if __name__ == "__main__":
    unittest.main()
