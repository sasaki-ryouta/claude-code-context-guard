import unittest

from routeforge.cache import cache_key
from routeforge.model import Event


class TestCacheKey(unittest.TestCase):
    def test_cache_key_contains_identity_fields(self):
        event = Event("tenant", "evt-1", "created", {})
        self.assertEqual(cache_key(event), "tenant|evt-1|created")


if __name__ == "__main__":
    unittest.main()
