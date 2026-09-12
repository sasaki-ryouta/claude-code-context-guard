import unittest

from routeforge.export import export_records
from routeforge.model import Event


class TestExport(unittest.TestCase):
    def test_export_shape_is_stable(self):
        rows = export_records([Event("Tenant", "evt-1", "created", {"x": 1})])
        self.assertEqual(
            rows,
            [
                {
                    "tenant": "Tenant",
                    "id": "evt-1",
                    "type": "created",
                    "payload": {"x": 1},
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
