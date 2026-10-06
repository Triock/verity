import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from specctl.spec import SpecError
from specctl.v2_source import load_v2_sources


LAYERS = ("product", "behavior", "system", "data", "blueprints", "verification")


def write_layers(directory):
    root = Path(directory)
    index = {"version": 2, "id": "sample", "layers": {name: f"{name}.json" for name in LAYERS}}
    (root / "solution.json").write_text(json.dumps(index))
    for name in LAYERS:
        (root / f"{name}.json").write_text('{"version":1}')
    return root / "solution.json"


class V2SourceTests(unittest.TestCase):
    def test_hashes_exact_bytes_of_all_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            index = write_layers(directory)
            sources = load_v2_sources(index)
            self.assertEqual(sources.id, "sample")
            self.assertEqual(set(sources.layers), set(LAYERS))
            self.assertEqual(sources.source_sha256["solution.json"], hashlib.sha256(index.read_bytes()).hexdigest())
            self.assertEqual(sources.source_sha256["product.json"], hashlib.sha256((index.parent / "product.json").read_bytes()).hexdigest())

    def test_names_index_digest_with_actual_index_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            index = write_layers(directory)
            candidate = index.with_name("candidate.json")
            index.rename(candidate)
            sources = load_v2_sources(candidate)
            self.assertEqual(sources.source_sha256["candidate.json"], hashlib.sha256(candidate.read_bytes()).hexdigest())
            self.assertNotIn("solution.json", sources.source_sha256)

    def test_rejects_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            index = write_layers(directory)
            (index.parent / "product.json").write_text('{"version":1,"version":1}')
            with self.assertRaisesRegex(SpecError, "product.json.*duplicate JSON key"):
                load_v2_sources(index)

    def test_rejects_non_json_numeric_constant(self):
        with tempfile.TemporaryDirectory() as directory:
            index = write_layers(directory)
            (index.parent / "product.json").write_text('{"version":1,"value":NaN}')
            with self.assertRaisesRegex(SpecError, "product.json.*NaN"):
                load_v2_sources(index)

    def test_rejects_nonfinite_exponent(self):
        with tempfile.TemporaryDirectory() as directory:
            index = write_layers(directory)
            (index.parent / "product.json").write_text('{"version":1,"value":1e999}')
            with self.assertRaisesRegex(SpecError, "product.json.*non-finite"):
                load_v2_sources(index)

    def test_rejects_missing_layer(self):
        with tempfile.TemporaryDirectory() as directory:
            index = write_layers(directory)
            (index.parent / "product.json").unlink()
            with self.assertRaisesRegex(SpecError, "product.json"):
                load_v2_sources(index)

    def test_rejects_parent_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            index = write_layers(directory)
            raw = json.loads(index.read_text())
            raw["layers"]["product"] = "../product.json"
            index.write_text(json.dumps(raw))
            with self.assertRaisesRegex(SpecError, "layers.product.*parent traversal"):
                load_v2_sources(index)

    def test_rejects_absolute_path(self):
        with tempfile.TemporaryDirectory() as directory:
            index = write_layers(directory)
            raw = json.loads(index.read_text())
            raw["layers"]["product"] = str(index.parent / "product.json")
            index.write_text(json.dumps(raw))
            with self.assertRaisesRegex(SpecError, "layers.product.*relative"):
                load_v2_sources(index)

    def test_rejects_symlink_escape(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            index = write_layers(directory)
            (index.parent / "product.json").unlink()
            target = Path(outside) / "product.json"
            target.write_text('{"version":1}')
            (index.parent / "product.json").symlink_to(target)
            with self.assertRaisesRegex(SpecError, "layers.product.*escapes"):
                load_v2_sources(index)


if __name__ == "__main__":
    unittest.main()
