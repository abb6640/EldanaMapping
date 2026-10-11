import unittest
from pathlib import Path

from backend.egglog_engine import match_demo_records


class EgglogMatchingTests(unittest.TestCase):
    def test_demo_records_produce_skill_and_shift_matches(self):
        result = match_demo_records(Path(__file__).parents[1] / "backend" / "demo_data")

        self.assertIn(result["engine"], {"egglog", "compatible-fallback"})
        self.assertGreaterEqual(result["count"], 14)
        self.assertEqual(result["rule"], "shared skill + same day + same shift")
        self.assertTrue(all(match["skill"] for match in result["matches"]))
