import json
import unittest

from specctl.release import ReleaseError, compile_release
from specctl.spec import parse_spec


def example_spec():
    return parse_spec(
        {
            "version": 1,
            "id": "example",
            "components": [
                {
                    "id": "app",
                    "kind": "application",
                    "language": "python",
                    "depends_on": ["library"],
                    "data_sets": [],
                },
                {
                    "id": "library",
                    "kind": "library",
                    "language": "python",
                    "depends_on": [],
                    "data_sets": [],
                },
            ],
            "data_sets": [],
        }
    )


class ReleaseTests(unittest.TestCase):
    def test_lock_contains_every_component_in_build_order(self):
        lock = compile_release(
            example_spec(), "a" * 64, {"app": "b" * 64, "library": "c" * 64}
        )
        self.assertEqual(lock["solution_id"], "example")
        self.assertEqual(lock["spec_sha256"], "a" * 64)
        self.assertEqual(
            lock["components"],
            [
                {"id": "library", "artifact_sha256": "c" * 64, "depends_on": []},
                {"id": "app", "artifact_sha256": "b" * 64, "depends_on": ["library"]},
            ],
        )

    def test_rejects_missing_artifact(self):
        with self.assertRaisesRegex(ReleaseError, "missing.*library"):
            compile_release(example_spec(), "a" * 64, {"app": "b" * 64})

    def test_rejects_extra_artifact(self):
        with self.assertRaisesRegex(ReleaseError, "extra.*stranger"):
            compile_release(
                example_spec(),
                "a" * 64,
                {"app": "b" * 64, "library": "c" * 64, "stranger": "d" * 64},
            )

    def test_rejects_malformed_artifact_digest(self):
        with self.assertRaisesRegex(ReleaseError, "app.*SHA-256"):
            compile_release(example_spec(), "a" * 64, {"app": "bad", "library": "c" * 64})

    def test_rejects_malformed_spec_digest(self):
        with self.assertRaisesRegex(ReleaseError, "spec.*SHA-256"):
            compile_release(example_spec(), "bad", {"app": "b" * 64, "library": "c" * 64})

    def test_lock_bytes_are_independent_of_artifact_map_order(self):
        first = compile_release(
            example_spec(), "a" * 64, {"app": "b" * 64, "library": "c" * 64}
        )
        second = compile_release(
            example_spec(), "a" * 64, {"library": "c" * 64, "app": "b" * 64}
        )
        canonical = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":"))
        self.assertEqual(canonical(first), canonical(second))


if __name__ == "__main__":
    unittest.main()
