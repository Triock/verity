import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from specctl.candidate import build_candidate, plan_candidate, verify_current
from specctl.spec import SpecError


SOURCE_ROOT = Path(__file__).resolve().parents[1]


def git(repo, *args):
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def candidate_repo(directory):
    repo = Path(directory)
    shutil.copytree(SOURCE_ROOT / "spec", repo / "spec")
    shutil.copytree(SOURCE_ROOT / "src" / "specctl", repo / "src" / "specctl", ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "generated_catalog.py"))
    (repo / "tools").mkdir()
    shutil.copy2(SOURCE_ROOT / "tools" / "catalog-python.json", repo / "tools" / "catalog-python.json")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_smoke.py").write_text("import unittest\n\nclass Smoke(unittest.TestCase):\n    def test_works(self):\n        self.assertTrue(True)\n")
    git(repo, "init", "-q")
    git(repo, "add", ".")
    git(repo, "-c", "user.name=Richard Hillman", "-c", "user.email=triock@gmail.com", "commit", "-qm", "fixture")
    return repo, git(repo, "rev-parse", "HEAD")


class CandidateTests(unittest.TestCase):
    def test_plan_pins_exact_committed_sources_and_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            repo, revision = candidate_repo(directory)
            record = plan_candidate(repo / "spec" / "solution.json", revision, repo)
            self.assertEqual(record["spec_revision"], revision)
            self.assertEqual(record["component_id"], "component-catalog")
            self.assertEqual(record["source_sha256"]["product.json"], hashlib.sha256((repo / "spec" / "product.json").read_bytes()).hexdigest())
            self.assertEqual(record["generator"]["sha256"], hashlib.sha256((repo / "src" / "specctl" / "catalog_generator.py").read_bytes()).hexdigest())
            self.assertEqual(len(record["candidate_id"]), 64)
            self.assertEqual(record, plan_candidate(repo / "spec" / "solution.json", revision, repo))

    def test_rejects_uncommitted_spec_or_tool_change(self):
        with tempfile.TemporaryDirectory() as directory:
            repo, revision = candidate_repo(directory)
            product = repo / "spec" / "product.json"
            product.write_text(product.read_text() + "\n")
            with self.assertRaisesRegex(SpecError, "product.json.*revision"):
                plan_candidate(repo / "spec" / "solution.json", revision, repo)
            git(repo, "checkout", "--", "spec/product.json")
            generator = repo / "src" / "specctl" / "catalog_generator.py"
            generator.write_text(generator.read_text() + "\n")
            with self.assertRaisesRegex(SpecError, "catalog_generator.py.*revision"):
                plan_candidate(repo / "spec" / "solution.json", revision, repo)

    def test_rejects_unknown_revision_and_wrong_pin(self):
        with tempfile.TemporaryDirectory() as directory:
            repo, revision = candidate_repo(directory)
            with self.assertRaisesRegex(SpecError, "revision"):
                plan_candidate(repo / "spec" / "solution.json", "0" * 40, repo)
            blueprint = repo / "spec" / "blueprints.json"
            raw = json.loads(blueprint.read_text())
            generated = next(item for item in raw["components"] if item["mode"] == "generated")
            generated["generator"]["sha256"] = "0" * 64
            blueprint.write_text(json.dumps(raw))
            git(repo, "add", ".")
            git(repo, "-c", "user.name=Richard Hillman", "-c", "user.email=triock@gmail.com", "commit", "-qm", "wrong pin")
            with self.assertRaisesRegex(SpecError, "generator.*digest"):
                plan_candidate(repo / "spec" / "solution.json", git(repo, "rev-parse", "HEAD"), repo)

    def test_build_reconstructs_exact_bytes_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            repo, revision = candidate_repo(directory)
            record = build_candidate(repo / "spec" / "solution.json", revision, repo)
            artifact = repo / record["artifact"]["path"]
            first = artifact.read_bytes()
            self.assertEqual(record["artifact"]["sha256"], hashlib.sha256(first).hexdigest())
            self.assertEqual(verify_current(repo)["candidate_id"], record["candidate_id"])
            artifact.unlink()
            self.assertEqual(build_candidate(repo / "spec" / "solution.json", revision, repo), record)
            self.assertEqual(artifact.read_bytes(), first)
            artifact.write_bytes(b"tampered")
            with self.assertRaisesRegex(SpecError, "artifact"):
                verify_current(repo)


if __name__ == "__main__":
    unittest.main()
