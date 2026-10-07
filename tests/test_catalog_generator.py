import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from specctl.v2_resolve import resolve_v2
from specctl.catalog_generator import generate_catalog


INDEX = Path(__file__).resolve().parents[1] / "spec" / "solution.json"


class CatalogGeneratorTests(unittest.TestCase):
    def test_generated_module_answers_from_resolved_contracts(self):
        resolved = resolve_v2(INDEX)["resolved"]
        source = generate_catalog(resolved)
        with tempfile.TemporaryDirectory() as directory:
            module = Path(directory) / "generated_catalog.py"
            module.write_bytes(source)
            probe = (
                "import importlib.util,json,sys; "
                "s=importlib.util.spec_from_file_location('catalog',sys.argv[1]); "
                "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
                "print(json.dumps({'ids':m.list_components(),'record':m.get_component('spec-model')},sort_keys=True))"
            )
            output = subprocess.check_output([sys.executable, "-c", probe, str(module)], text=True)
        result = json.loads(output)
        self.assertEqual(result["record"], {
            "id": "spec-model", "kind": "library", "language": "python",
            "depends_on": [], "data_sets": [], "implements": ["validate-model"],
            "provides": [{"contract_id": "validated-spec", "revision": "1"}], "requires": [],
        })
        self.assertIn("specctl", result["ids"])

    def test_output_is_independent_of_component_record_order(self):
        resolved = resolve_v2(INDEX)["resolved"]
        first = generate_catalog(resolved)
        resolved["layers"]["system"]["components"].reverse()
        self.assertEqual(first, generate_catalog(resolved))


if __name__ == "__main__":
    unittest.main()
