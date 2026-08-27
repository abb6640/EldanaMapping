import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class ProjectSmokeTests(unittest.TestCase):
    def test_project_has_expected_entrypoints(self):
        self.assertTrue((ROOT / "app" / "__main__.py").exists())
        self.assertTrue((ROOT / "web" / "index.html").exists())


    def test_landing_page_contains_product_name(self):
        page = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn("EldanaMapping", page)
        self.assertIn("Explore the map", page)
