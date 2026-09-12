import unittest

from routeforge.parse import parse_legacy_a, parse_legacy_b


class TestLegacyParsers(unittest.TestCase):
    def test_legacy_a_uses_canonical_field_rules(self):
        event = parse_legacy_a(
            {
                "tenant": " Acme ",
                "id": "evt-1",
                "type": " CREATED ",
                "payload": {"x": 1},
            }
        )
        self.assertEqual(event.tenant_id, "Acme")
        self.assertEqual(event.external_id, "evt-1")
        self.assertEqual(event.event_type, "created")
        self.assertEqual(event.payload, {"x": 1})

    def test_legacy_b_empty_account_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_legacy_b(
                {
                    "account": "   ",
                    "id": "evt-2",
                    "kind": "updated",
                    "payload": {},
                }
            )

    def test_legacy_b_basic_shape(self):
        event = parse_legacy_b(
            {
                "account": "Beta",
                "id": "evt-3",
                "kind": "UPDATED",
                "payload": {"ok": True},
            }
        )
        self.assertEqual(event.tenant_id, "Beta")
        self.assertEqual(event.external_id, "evt-3")
        self.assertEqual(event.event_type, "updated")


if __name__ == "__main__":
    unittest.main()
