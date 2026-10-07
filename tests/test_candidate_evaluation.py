import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from specctl.candidate import build_candidate, verify_current
from specctl.spec import SpecError
from tests.test_candidate import candidate_repo, git


def cli(repo, *args):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo / "src")
    return subprocess.run([sys.executable, "-m", "specctl", *args], cwd=repo, env=env, text=True, capture_output=True)


class CandidateEvaluationTests(unittest.TestCase):
    def test_catalog_command_returns_spec_declared_record(self):
        with tempfile.TemporaryDirectory() as directory:
            repo, revision = candidate_repo(directory)
            build_candidate(repo / "spec" / "solution.json", revision, repo)
            result = cli(repo, "catalog", "spec-model")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["provides"], [{"contract_id": "validated-spec", "revision": "1"}])

    def test_missing_generated_module_gives_rebuild_instruction(self):
        with tempfile.TemporaryDirectory() as directory:
            repo, _ = candidate_repo(directory)
            result = cli(repo, "catalog", "spec-model")
            self.assertEqual(result.returncode, 2)
            self.assertIn("candidate build", result.stderr)

    def test_verify_current_without_candidate_is_actionable(self):
        with tempfile.TemporaryDirectory() as directory:
            repo, _ = candidate_repo(directory)
            result = cli(repo, "candidate", "verify-current")
            self.assertEqual(result.returncode, 2)
            self.assertIn("current candidate", result.stderr)

    def test_build_records_submitted_input_observation_and_unit_tests(self):
        with tempfile.TemporaryDirectory() as directory:
            repo, revision = candidate_repo(directory)
            record = build_candidate(repo / "spec" / "solution.json", revision, repo)
            evidence_path = repo / ".verity" / "candidates" / record["candidate_id"] / "evidence.json"
            evidence = json.loads(evidence_path.read_text())
            self.assertEqual(evidence["status"], "passed")
            self.assertEqual(evidence["acceptance"]["input"], {"command": "catalog", "component_id": "spec-model"})
            self.assertEqual(evidence["acceptance"]["observed"], evidence["acceptance"]["expected"])
            self.assertEqual(evidence["tests"]["exit_code"], 0)
            self.assertEqual(verify_current(repo)["candidate_id"], record["candidate_id"])

    def test_wrong_expected_response_never_produces_passing_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            repo, _ = candidate_repo(directory)
            case_file = repo / "spec" / "verification.json"
            raw = json.loads(case_file.read_text())
            case = next(case for case in raw["cases"] if case["id"] == "query-component-catalog")
            case["expected"]["value"]["kind"] = "service"
            case_file.write_text(json.dumps(raw))
            git(repo, "add", ".")
            git(repo, "-c", "user.name=Richard Hillman", "-c", "user.email=triock@gmail.com", "commit", "-qm", "wrong expected")
            revision = git(repo, "rev-parse", "HEAD")
            with self.assertRaisesRegex(SpecError, "acceptance"):
                build_candidate(repo / "spec" / "solution.json", revision, repo)
            self.assertFalse(list((repo / ".verity" / "candidates").glob("*/evidence.json")))

    def test_failing_test_suite_never_produces_passing_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            repo, revision = candidate_repo(directory)
            (repo / "tests" / "test_smoke.py").write_text("import unittest\n\nclass Smoke(unittest.TestCase):\n    def test_works(self):\n        self.fail('broken')\n")
            with self.assertRaisesRegex(SpecError, "unit tests"):
                build_candidate(repo / "spec" / "solution.json", revision, repo)
            self.assertFalse(list((repo / ".verity" / "candidates").glob("*/evidence.json")))

    def test_failed_new_candidate_preserves_previous_current_pointer(self):
        with tempfile.TemporaryDirectory() as directory:
            repo, revision = candidate_repo(directory)
            first = build_candidate(repo / "spec" / "solution.json", revision, repo)
            pointer = repo / ".verity" / "candidates" / "current.json"
            before = pointer.read_bytes()
            product = repo / "spec" / "product.json"
            product.write_text(product.read_text().replace("Inspect declared", "Review declared"))
            git(repo, "add", ".")
            git(repo, "-c", "user.name=Richard Hillman", "-c", "user.email=triock@gmail.com", "commit", "-qm", "new intent")
            (repo / "tests" / "test_smoke.py").write_text("import unittest\n\nclass Smoke(unittest.TestCase):\n    def test_works(self):\n        self.fail('broken')\n")
            with self.assertRaisesRegex(SpecError, "unit tests"):
                build_candidate(repo / "spec" / "solution.json", git(repo, "rev-parse", "HEAD"), repo)
            self.assertEqual(pointer.read_bytes(), before)
            self.assertEqual(json.loads(before)["candidate_id"], first["candidate_id"])

    def test_verify_rejects_altered_evidence_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            repo, revision = candidate_repo(directory)
            record = build_candidate(repo / "spec" / "solution.json", revision, repo)
            path = repo / ".verity" / "candidates" / record["candidate_id"] / "evidence.json"
            original = json.loads(path.read_text())
            for section, field, value in (
                ("tests", "command", "false"),
                ("tests", "stderr_sha256", "0" * 64),
                (None, "python_version", "9.9.9"),
            ):
                with self.subTest(field=field):
                    altered = json.loads(json.dumps(original))
                    target = altered if section is None else altered[section]
                    target[field] = value
                    path.write_text(json.dumps(altered))
                    with self.assertRaisesRegex(SpecError, "evidence"):
                        verify_current(repo)


if __name__ == "__main__":
    unittest.main()
