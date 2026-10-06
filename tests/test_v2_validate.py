import copy
import unittest

from specctl.spec import SpecError
from specctl.v2_source import V2Sources
from specctl.v2_validate import validate_v2


def valid_bundle():
    layers = {
        "product": {"version": 1, "actors": [{"id": "user", "name": "User"}], "use_cases": [{"id": "run", "actor_id": "user", "goal": "Run"}]},
        "behavior": {"version": 1, "requirements": [{"id": "req", "use_case_id": "run", "statement": "Execute", "contract_ids": ["api"]}], "contracts": [{"id": "api", "revision": "1", "description": "API"}]},
        "system": {"version": 1, "components": [
            {"id": "lib", "kind": "library", "language": "python", "depends_on": [], "data_sets": ["store"], "implements": ["req"], "provides": ["api"], "requires": []},
            {"id": "app", "kind": "application", "language": "python", "depends_on": ["lib"], "data_sets": [], "implements": [], "provides": [], "requires": [{"contract_id": "api", "accepted_revisions": ["1"]}]},
        ]},
        "data": {"version": 1, "data_sets": [{"id": "store", "owner": "lib", "schema_version": 1, "invariants": ["rows reconcile"], "retention_days": 30, "migration": {"strategy": "expand", "rollback": "restore"}, "recovery": {"rpo_minutes": 5, "rto_minutes": 30, "backup_retention_days": 30}}]},
        "blueprints": {"version": 1, "components": [
            {"component_id": "lib", "mode": "generated", "generator": {"id": "gen", "version": "1", "sha256": "A" * 64}, "toolchains": {"python": "B" * 64}, "inputs": {}, "requirements": ["req"], "contracts": ["api"]},
            {"component_id": "app", "mode": "bootstrap", "source_path": "src/app"},
        ]},
        "verification": {"version": 1, "cases": [{"id": "case", "requirement_ids": ["req"], "target_component": "lib", "modality": "cli", "input": {"arg": "go"}, "expected": {"kind": "exact", "value": "ok"}}]},
    }
    return V2Sources("sample", layers, {})


class V2ValidationTests(unittest.TestCase):
    def test_links_all_layers_and_projects_graph(self):
        bundle = valid_bundle()
        original = copy.deepcopy(bundle.layers)
        result = validate_v2(bundle)
        self.assertEqual(result.graph.id, "sample")
        self.assertEqual(len(result.graph.components), 2)
        self.assertEqual(result.bootstrap_components, ("app",))
        self.assertEqual(result.resolved["layers"]["blueprints"]["components"][1]["mode"], "bootstrap")
        self.assertEqual(bundle.layers, original)

    def test_rejects_unknown_references(self):
        cases = [
            ("behavior", "requirements", 0, "use_case_id", "missing-use-case"),
            ("system", "components", 0, "implements", ["missing-requirement"]),
            ("system", "components", 0, "provides", ["missing-contract"]),
            ("system", "components", 0, "data_sets", ["missing-dataset"]),
            ("data", "data_sets", 0, "owner", "missing-owner"),
            ("verification", "cases", 0, "target_component", "missing-target"),
            ("blueprints", "components", 0, "component_id", "missing-component"),
        ]
        for layer, collection, index, field, value in cases:
            with self.subTest(field=field):
                bundle = valid_bundle()
                bundle.layers[layer][collection][index][field] = value
                with self.assertRaisesRegex(SpecError, "missing"):
                    validate_v2(bundle)

    def test_rejects_missing_blueprint(self):
        bundle = valid_bundle()
        bundle.layers["blueprints"]["components"].pop()
        with self.assertRaisesRegex(SpecError, "blueprint.*app"):
            validate_v2(bundle)

    def test_rejects_duplicate_ids_and_cycle(self):
        bundle = valid_bundle()
        bundle.layers["product"]["actors"].append(copy.deepcopy(bundle.layers["product"]["actors"][0]))
        with self.assertRaisesRegex(SpecError, "duplicate.*user"):
            validate_v2(bundle)
        bundle = valid_bundle()
        bundle.layers["system"]["components"][0]["depends_on"] = ["app"]
        with self.assertRaisesRegex(SpecError, "dependency cycle"):
            validate_v2(bundle)

    def test_requires_complete_data_policy(self):
        for section, field in (("migration", "rollback"), ("recovery", "backup_retention_days")):
            with self.subTest(field=field):
                bundle = valid_bundle()
                del bundle.layers["data"]["data_sets"][0][section][field]
                with self.assertRaisesRegex(SpecError, field):
                    validate_v2(bundle)

    def test_rejects_invalid_generator_pins(self):
        for field, value in (("sha256", "bad"),):
            bundle = valid_bundle()
            bundle.layers["blueprints"]["components"][0]["generator"][field] = value
            with self.assertRaisesRegex(SpecError, field):
                validate_v2(bundle)
        bundle = valid_bundle()
        bundle.layers["blueprints"]["components"][0]["toolchains"]["python"] = "bad"
        with self.assertRaisesRegex(SpecError, "toolchains"):
            validate_v2(bundle)

    def test_rejects_provider_or_revision_mismatch(self):
        bundle = valid_bundle()
        bundle.layers["system"]["components"][1]["depends_on"] = []
        with self.assertRaisesRegex(SpecError, "provider"):
            validate_v2(bundle)
        bundle = valid_bundle()
        bundle.layers["system"]["components"][1]["requires"][0]["accepted_revisions"] = ["2"]
        with self.assertRaisesRegex(SpecError, "revision"):
            validate_v2(bundle)

    def test_requires_requirement_implementation_and_acceptance(self):
        bundle = valid_bundle()
        bundle.layers["system"]["components"][0]["implements"] = []
        with self.assertRaisesRegex(SpecError, "req.*implement"):
            validate_v2(bundle)
        bundle = valid_bundle()
        bundle.layers["verification"]["cases"] = []
        with self.assertRaisesRegex(SpecError, "req.*acceptance"):
            validate_v2(bundle)

    def test_acceptance_case_must_target_an_implementer(self):
        bundle = valid_bundle()
        bundle.layers["verification"]["cases"][0]["target_component"] = "app"
        with self.assertRaisesRegex(SpecError, "case.*req.*implement"):
            validate_v2(bundle)


if __name__ == "__main__":
    unittest.main()
