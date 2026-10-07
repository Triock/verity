import copy
import json
import tempfile
import unittest
from pathlib import Path

from specctl.v2_resolve import resolve_v2
from tests.test_v2_validate import valid_bundle


def write_bundle(directory, bundle, indent=None):
    root = Path(directory)
    index = {"version": 2, "id": bundle.id, "layers": {name: f"{name}.json" for name in bundle.layers}}
    (root / "solution.json").write_text(json.dumps(index, indent=indent))
    for name, layer in bundle.layers.items():
        (root / f"{name}.json").write_text(json.dumps(layer, indent=indent))
    return root / "solution.json"


class V2ResolveTests(unittest.TestCase):
    def test_order_formatting_and_digest_case_do_not_change_semantic_digest(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            base = valid_bundle()
            first_result = resolve_v2(write_bundle(first, base))
            variant = copy.deepcopy(base)
            variant.layers["system"]["components"].reverse()
            variant.layers["blueprints"]["components"].reverse()
            variant.layers["blueprints"]["components"][1]["generator"]["sha256"] = "a" * 64
            variant.layers["blueprints"]["components"][1]["toolchains"]["python"] = "b" * 64
            second_result = resolve_v2(write_bundle(second, variant, indent=2))
        self.assertEqual(first_result["resolved_sha256"], second_result["resolved_sha256"])
        self.assertNotEqual(first_result["source_sha256"], second_result["source_sha256"])
        self.assertEqual(first_result["bootstrap_components"], ["app"])
        self.assertEqual([c["id"] for c in first_result["resolved"]["layers"]["system"]["components"]], ["lib", "app"])

    def test_semantic_changes_change_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = valid_bundle()
            before = resolve_v2(write_bundle(directory, bundle))["resolved_sha256"]
            for layer, field, value in (
                ("behavior", "statement", "Execute reliably"),
                ("behavior", "revision", "2"),
                ("blueprints", "sha256", "c" * 64),
            ):
                changed = copy.deepcopy(bundle)
                if field == "statement":
                    changed.layers[layer]["requirements"][0][field] = value
                elif field == "revision":
                    changed.layers[layer]["contracts"][0][field] = value
                    changed.layers["system"]["components"][1]["requires"][0]["accepted_revisions"] = [value]
                else:
                    changed.layers[layer]["components"][0]["generator"][field] = value
                after = resolve_v2(write_bundle(directory, changed))["resolved_sha256"]
                self.assertNotEqual(before, after, field)


if __name__ == "__main__":
    unittest.main()
