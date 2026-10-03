import copy
import unittest
from pathlib import Path

from specctl.spec import SpecError, load_spec, parse_spec


def valid_raw():
    return {
        "version": 1,
        "id": "manager",
        "components": [
            {
                "id": "model",
                "kind": "library",
                "language": "python",
                "depends_on": [],
                "data_sets": [],
            },
            {
                "id": "app",
                "kind": "application",
                "language": "python",
                "depends_on": ["model"],
                "data_sets": ["history"],
            },
        ],
        "data_sets": [
            {
                "id": "history",
                "owner": "app",
                "recovery": {"rpo_minutes": 5, "rto_minutes": 30},
            }
        ],
    }


class SpecTests(unittest.TestCase):
    def test_loads_the_management_service_spec(self):
        path = Path(__file__).resolve().parents[1] / "spec" / "solution.json"
        spec = load_spec(path)
        self.assertEqual(spec.id, "software-manager")
        self.assertEqual({component.id for component in spec.components}, {"spec-model", "specctl"})

    def test_rejects_duplicate_component_ids(self):
        raw = valid_raw()
        raw["components"].append(copy.deepcopy(raw["components"][0]))
        with self.assertRaisesRegex(SpecError, "duplicate component.*model"):
            parse_spec(raw)

    def test_rejects_unknown_dependency(self):
        raw = valid_raw()
        raw["components"][1]["depends_on"] = ["missing"]
        with self.assertRaisesRegex(SpecError, "app.*unknown dependency.*missing"):
            parse_spec(raw)

    def test_rejects_dependency_cycle(self):
        raw = valid_raw()
        raw["components"][0]["depends_on"] = ["app"]
        with self.assertRaisesRegex(SpecError, "cycle"):
            parse_spec(raw)

    def test_rejects_unknown_dataset_owner(self):
        raw = valid_raw()
        raw["data_sets"][0]["owner"] = "missing"
        with self.assertRaisesRegex(SpecError, "history.*owner.*missing"):
            parse_spec(raw)

    def test_rejects_missing_recovery_contract(self):
        raw = valid_raw()
        raw["data_sets"][0].pop("recovery")
        with self.assertRaisesRegex(SpecError, "history.*recovery"):
            parse_spec(raw)

    def test_rejects_unknown_dataset_reference(self):
        raw = valid_raw()
        raw["components"][1]["data_sets"] = ["missing"]
        with self.assertRaisesRegex(SpecError, "app.*unknown data set.*missing"):
            parse_spec(raw)

    def test_rejects_negative_recovery_target(self):
        raw = valid_raw()
        raw["data_sets"][0]["recovery"]["rpo_minutes"] = -1
        with self.assertRaisesRegex(SpecError, "history.*rpo_minutes"):
            parse_spec(raw)


if __name__ == "__main__":
    unittest.main()
