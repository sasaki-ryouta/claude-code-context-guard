import unittest

from routeforge.normalize import normalize_event


class TestNormalizeEvent(unittest.TestCase):
    def test_required_fields_are_stripped_and_event_type_is_canonical(self):
        event = normalize_event(
            {
                "tenant_id": " T1 ",
                "external_id": "ext-1",
                "event_type": " CREATE ",
                "payload": {"n": 1},
            }
        )
        self.assertEqual(event.tenant_id, "T1")
        self.assertEqual(event.external_id, "ext-1")
        self.assertEqual(event.event_type, "create")

    def test_missing_required_field_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_event(
                {
                    "tenant_id": "T1",
                    "external_id": "ext-1",
                    "payload": {},
                }
            )


if __name__ == "__main__":
    unittest.main()
