import json
import tempfile
import unittest

from tests.test_cli import SPEC_PATH, run_cli
from tests.test_v2_resolve import write_bundle
from tests.test_v2_validate import valid_bundle


class V2CliTests(unittest.TestCase):
    def test_v2_validate_order_impact_and_resolve(self):
        with tempfile.TemporaryDirectory() as directory:
            index = write_bundle(directory, valid_bundle())
            for args, expected in (
                (["validate", str(index)], {"solution_id": "sample", "components": 2, "data_sets": 1}),
                (["order", str(index)], ["lib", "app"]),
                (["impact", str(index), "lib", "--direction", "consumers"], ["lib", "app"]),
            ):
                with self.subTest(args=args):
                    code, output, errors = run_cli(args)
                    self.assertEqual((code, errors), (0, ""))
                    self.assertEqual(json.loads(output), expected)
            code, output, errors = run_cli(["resolve", str(index)])
            self.assertEqual((code, errors), (0, ""))
            self.assertEqual(json.loads(output)["resolved"]["version"], 2)

    def test_resolve_rejects_v1_and_lock_rejects_v2(self):
        code, output, errors = run_cli(["resolve", str(SPEC_PATH)])
        self.assertEqual((code, output), (2, ""))
        self.assertIn("v2", errors)
        with tempfile.TemporaryDirectory() as directory:
            index = write_bundle(directory, valid_bundle())
            code, output, errors = run_cli(["lock", str(index), "missing-artifacts.json"])
        self.assertEqual((code, output), (2, ""))
        self.assertIn("v2 release locks are not supported yet", errors)


if __name__ == "__main__":
    unittest.main()
