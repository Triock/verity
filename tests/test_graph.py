import unittest

from specctl.graph import build_order, change_impact
from specctl.spec import SpecError, parse_spec


def component(component_id, dependencies):
    return {
        "id": component_id,
        "kind": "library",
        "language": "python",
        "depends_on": dependencies,
        "data_sets": [],
    }


def graph_spec(components=None):
    return parse_spec(
        {
            "version": 1,
            "id": "graph-test",
            "components": components
            or [
                component("app", ["service"]),
                component("service", ["foundation"]),
                component("foundation", []),
            ],
            "data_sets": [],
        }
    )


class GraphTests(unittest.TestCase):
    def test_build_order_puts_dependencies_before_consumers(self):
        self.assertEqual(build_order(graph_spec()), ("foundation", "service", "app"))

    def test_build_order_uses_lexicographic_ties(self):
        spec = graph_spec(
            [component("z", []), component("app", ["z", "a"]), component("a", [])]
        )
        self.assertEqual(build_order(spec), ("a", "z", "app"))

    def test_library_change_reaches_all_consumers(self):
        self.assertEqual(
            change_impact(graph_spec(), "foundation", "consumers"),
            ("foundation", "service", "app"),
        )

    def test_app_requirement_reaches_dependencies(self):
        self.assertEqual(
            change_impact(graph_spec(), "app", "dependencies"),
            ("foundation", "service", "app"),
        )

    def test_bidirectional_impact_reaches_siblings_through_shared_foundation(self):
        spec = graph_spec(
            [
                component("app-a", ["foundation"]),
                component("app-b", ["foundation"]),
                component("foundation", []),
            ]
        )
        self.assertEqual(
            change_impact(spec, "app-a", "both"),
            ("foundation", "app-a", "app-b"),
        )

    def test_unknown_component_is_rejected(self):
        with self.assertRaisesRegex(SpecError, "unknown component.*missing"):
            change_impact(graph_spec(), "missing", "both")

    def test_unknown_direction_is_rejected(self):
        with self.assertRaisesRegex(SpecError, "unknown direction.*sideways"):
            change_impact(graph_spec(), "app", "sideways")


if __name__ == "__main__":
    unittest.main()
