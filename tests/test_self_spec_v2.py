import unittest
from pathlib import Path

from specctl.v2_resolve import resolve_v2


INDEX = Path(__file__).resolve().parents[1] / "spec" / "solution.json"


class SelfSpecTests(unittest.TestCase):
    def test_self_spec_links_product_behavior_and_verification(self):
        envelope = resolve_v2(INDEX)
        layers = envelope["resolved"]["layers"]
        self.assertEqual(envelope["resolved"]["id"], "software-manager")
        self.assertEqual({item["id"] for item in layers["system"]["components"]}, {"spec-model", "component-catalog", "specctl"})
        self.assertTrue(layers["product"]["use_cases"])
        self.assertTrue(layers["behavior"]["requirements"])
        self.assertTrue(layers["behavior"]["contracts"])
        self.assertTrue(layers["verification"]["cases"])
        self.assertEqual(envelope["bootstrap_components"], ["spec-model", "specctl"])
        generated = [item for item in layers["blueprints"]["components"] if item["regenerable"]]
        self.assertEqual([item["component_id"] for item in generated], ["component-catalog"])

    def test_issue_intake_has_linked_behavior_and_durable_data_contract(self):
        layers = resolve_v2(INDEX)["resolved"]["layers"]
        use_cases = {item["id"] for item in layers["product"]["use_cases"]}
        requirements = {item["id"] for item in layers["behavior"]["requirements"]}
        contracts = {item["id"] for item in layers["behavior"]["contracts"]}
        components = {item["id"]: item for item in layers["system"]["components"]}
        datasets = {item["id"]: item for item in layers["data"]["data_sets"]}
        cases = {item["id"]: item for item in layers["verification"]["cases"]}
        self.assertIn("capture-issue", use_cases)
        self.assertIn("import-github-issue", requirements)
        self.assertIn("issue-intake", contracts)
        self.assertIn("import-github-issue", components["specctl"]["implements"])
        self.assertIn("issue-intake", components["specctl"]["provides"])
        self.assertEqual(datasets["issue-snapshots"]["owner"], "specctl")
        self.assertIn("issue-snapshots", components["specctl"]["data_sets"])
        self.assertEqual(cases["record-ready-github-issue"]["target_component"], "specctl")


if __name__ == "__main__":
    unittest.main()
