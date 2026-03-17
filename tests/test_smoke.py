from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_project_has_expected_entrypoints():
    assert (ROOT / "app" / "__main__.py").exists()
    assert (ROOT / "web" / "index.html").exists()


def test_landing_page_contains_product_name():
    page = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert "EldanaMapping" in page
    assert "Explore the map" in page
