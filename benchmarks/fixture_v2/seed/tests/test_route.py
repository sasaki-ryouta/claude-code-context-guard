import unittest

from routeforge.model import Event
from routeforge.route import route_events, routing_key


class TestRouting(unittest.TestCase):
    def test_routing_key_uses_public_identity_fields(self):
        event = Event("t2", "id-b", "created", {})
        self.assertEqual(routing_key(event), ("t2", "created", "id-b"))

    def test_events_are_sorted_by_routing_key(self):
        events = [
            Event("t2", "id-b", "created", {"timestamp": 2}),
            Event("t1", "id-a", "created", {"timestamp": 1}),
        ]
        routed = route_events(events)
        self.assertEqual([event.tenant_id for event in routed], ["t1", "t2"])


if __name__ == "__main__":
    unittest.main()
