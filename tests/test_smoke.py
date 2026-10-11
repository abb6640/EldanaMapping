import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class ProjectSmokeTests(unittest.TestCase):
    def test_project_has_expected_entrypoints(self):
        self.assertTrue((ROOT / "backend" / "main.py").exists())
        self.assertTrue((ROOT / "frontend" / "Eldana.html").exists())


    def test_landing_page_contains_product_name(self):
        page = (ROOT / "frontend" / "Eldana.html").read_text(encoding="utf-8")
        self.assertIn("Eldana", page)
        self.assertIn("Interactive Map", page)
