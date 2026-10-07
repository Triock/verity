import unittest
from pathlib import Path

from specctl.v2_resolve import resolve_v2


INDEX = Path(__file__).resolve().parents[1] / "spec" / "solution.json"


class SelfSpecTests(unittest.TestCase):
    def test_self_spec_links_product_behavior_and_verification(self):
        envelope = resolve_v2(INDEX)
        layers = envelope["resolved"]["layers"]
        self.assertEqual(envelope["resolved"]["id"], "software-manager")
        self.assertEqual({item["id"] for item in layers["system"]["components"]}, {"spec-model", "specctl"})
        self.assertTrue(layers["product"]["use_cases"])
        self.assertTrue(layers["behavior"]["requirements"])
        self.assertTrue(layers["behavior"]["contracts"])
        self.assertTrue(layers["verification"]["cases"])
        self.assertEqual(envelope["bootstrap_components"], ["spec-model", "specctl"])
        self.assertTrue(all(item["regenerable"] is False for item in layers["blueprints"]["components"]))


if __name__ == "__main__":
    unittest.main()
