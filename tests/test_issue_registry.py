import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from specctl.issue_registry import record_issue
from specctl.spec import SpecError


def snapshot(updated="2026-10-07T13:00:00Z", body="First report"):
    return {
        "version": 1,
        "source": {
            "provider": "github", "repository": "Triock/verity", "issue_id": 81,
            "number": 7, "url": "https://github.com/Triock/verity/issues/7",
            "updated_at": updated,
        },
        "title": "Recovery check", "body": body, "labels": ["verity:ready"],
    }


class IssueRegistryTests(unittest.TestCase):
    def test_records_replay_idempotently_and_advances_only_on_newer_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            first = record_issue(repo, snapshot())
            first_bytes = (repo / first["snapshot_path"]).read_bytes()
            pointer = repo / first["current_path"]
            before = pointer.read_bytes()
            self.assertEqual(json.loads(first_bytes)["body"], "First report")
            self.assertFalse(first["committed"])
            self.assertEqual(first, record_issue(repo, snapshot()))
            self.assertEqual(pointer.read_bytes(), before)

            second = record_issue(repo, snapshot("2026-10-07T14:00:00Z", "Revised report"))
            self.assertNotEqual(first["digest"], second["digest"])
            self.assertEqual(json.loads(pointer.read_text())["digest"], second["digest"])
            self.assertEqual((repo / first["snapshot_path"]).read_bytes(), first_bytes)
            with self.assertRaisesRegex(SpecError, "older"):
                record_issue(repo, snapshot())
            self.assertEqual(json.loads(pointer.read_text())["digest"], second["digest"])

    def test_rejects_same_timestamp_conflict_and_corrupt_existing_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            first = record_issue(repo, snapshot())
            pointer = (repo / first["current_path"]).read_bytes()
            with self.assertRaisesRegex(SpecError, "same update time"):
                record_issue(repo, snapshot(body="Different"))
            self.assertEqual((repo / first["current_path"]).read_bytes(), pointer)
            (repo / first["snapshot_path"]).write_text("tampered")
            with self.assertRaisesRegex(SpecError, "conflicts"):
                record_issue(repo, snapshot())

    def test_pointer_failure_preserves_prior_current_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            first = record_issue(repo, snapshot())
            pointer = repo / first["current_path"]
            before = pointer.read_bytes()
            actual_replace = os.replace

            def fail_pointer(source, dest):
                if Path(dest) == pointer:
                    raise OSError("simulated interruption")
                return actual_replace(source, dest)

            with patch("specctl.issue_registry.os.replace", side_effect=fail_pointer):
                with self.assertRaisesRegex(SpecError, "write"):
                    record_issue(repo, snapshot("2026-10-07T14:00:00Z"))
            self.assertEqual(pointer.read_bytes(), before)

    def test_rejects_tampered_current_snapshot_before_advancing(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            first = record_issue(repo, snapshot())
            pointer = repo / first["current_path"]
            before = pointer.read_bytes()
            current = repo / first["snapshot_path"]
            current.write_text(json.dumps({**snapshot(), "body": "tampered"}))
            with self.assertRaisesRegex(SpecError, "digest"):
                record_issue(repo, snapshot("2026-10-07T14:00:00Z"))
            self.assertEqual(pointer.read_bytes(), before)

    def test_rejects_symlinked_registry_path(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            repo = Path(directory)
            (repo / ".verity").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(SpecError, "symlink"):
                record_issue(repo, snapshot())
            self.assertEqual(list(Path(outside).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
