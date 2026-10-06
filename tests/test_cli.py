import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from specctl.cli import main


SPEC_PATH = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "solution-v1.json"


def run_cli(arguments):
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main(arguments)
    return code, stdout.getvalue(), stderr.getvalue()


class CliTests(unittest.TestCase):
    def test_validate_reports_the_self_spec(self):
        code, output, errors = run_cli(["validate", str(SPEC_PATH)])
        self.assertEqual(code, 0)
        self.assertEqual(errors, "")
        self.assertEqual(
            json.loads(output),
            {"solution_id": "software-manager", "components": 2, "data_sets": 0},
        )

    def test_order_reports_dependencies_first(self):
        code, output, errors = run_cli(["order", str(SPEC_PATH)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output), ["spec-model", "specctl"])
        self.assertEqual(errors, "")

    def test_impact_reports_library_consumers(self):
        code, output, errors = run_cli(
            ["impact", str(SPEC_PATH), "spec-model", "--direction", "consumers"]
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output), ["spec-model", "specctl"])
        self.assertEqual(errors, "")

    def test_invalid_spec_produces_actionable_error_without_stdout(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.json"
            path.write_text('{"version": 1, "id": "broken", "components": []}')
            code, output, errors = run_cli(["validate", str(path)])
        self.assertEqual(code, 2)
        self.assertEqual(output, "")
        self.assertIn("data_sets", errors)
        self.assertIn("broken.json", errors)

    def test_lock_pins_every_component_and_exact_spec_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            inventory_path = Path(directory) / "artifacts.json"
            inventory_path.write_text(
                json.dumps({"specctl": "b" * 64, "spec-model": "c" * 64})
            )
            code, output, errors = run_cli(
                ["lock", str(SPEC_PATH), str(inventory_path)]
            )
        self.assertEqual(code, 0)
        self.assertEqual(errors, "")
        lock = json.loads(output)
        self.assertEqual(lock["spec_sha256"], hashlib.sha256(SPEC_PATH.read_bytes()).hexdigest())
        self.assertEqual([entry["id"] for entry in lock["components"]], ["spec-model", "specctl"])

    def test_lock_rejects_duplicate_artifact_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            inventory_path = Path(directory) / "artifacts.json"
            inventory_path.write_text(
                '{"spec-model":"' + "a" * 64 + '","specctl":"' + "b" * 64
                + '","specctl":"' + "c" * 64 + '"}'
            )
            code, output, errors = run_cli(["lock", str(SPEC_PATH), str(inventory_path)])
        self.assertEqual(code, 2)
        self.assertEqual(output, "")
        self.assertIn("duplicate JSON key: specctl", errors)


if __name__ == "__main__":
    unittest.main()
