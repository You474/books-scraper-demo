#!/usr/bin/env python3
"""离线单测：列表页解析、价格/评分映射、详情页、导出转义与原子写。不打网络。"""

from __future__ import annotations

import csv
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import export  # noqa: E402
import scraper  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
LIST_URL = "https://books.toscrape.com/"


class TestParseList(unittest.TestCase):
    def test_first_page(self):
        html = (FIXTURES / "list-1.html").read_text(encoding="utf-8")
        rows, problems, next_href = scraper.parse_list_page(html, 1, LIST_URL)
        self.assertEqual(problems, [])
        self.assertEqual(len(rows), 20)
        first = rows[0]
        self.assertEqual(first["title"], "A Light in the Attic")           # 取 title 属性，不是截断文本
        self.assertEqual(first["price_gbp"], 51.77)
        self.assertEqual(first["rating"], 3)
        self.assertTrue(first["in_stock"])
        self.assertTrue(first["product_url"].startswith("https://books.toscrape.com/catalogue/"))
        self.assertTrue(first["image_url"].startswith("https://books.toscrape.com/media/"))
        self.assertTrue(re.fullmatch(r"[0-9a-f]{12}", first["book_id"]))
        self.assertEqual(next_href, "catalogue/page-2.html")

    def test_second_page(self):
        html = (FIXTURES / "list-2.html").read_text(encoding="utf-8")
        rows, problems, _next = scraper.parse_list_page(html, 2, LIST_URL + "catalogue/page-2.html")
        self.assertEqual(problems, [])
        self.assertEqual(len(rows), 20)
        self.assertTrue(all(r["page"] == 2 for r in rows))

    def test_missing_title_is_skipped(self):
        html = '<article class="product_pod"><p class="star-rating One"></p></article>'
        rows, problems, _n = scraper.parse_list_page(html, 1, LIST_URL)
        self.assertEqual(rows, [])
        self.assertEqual(problems[0]["reason"], "parse_missing_field")


class TestScalars(unittest.TestCase):
    def test_price(self):
        self.assertEqual(scraper.parse_price("£51.77"), 51.77)
        self.assertEqual(scraper.parse_price("Â£1,234.50"), 1234.50)
        self.assertEqual(scraper.parse_price("£0.99"), 0.99)
        self.assertIsNone(scraper.parse_price(""))
        self.assertIsNone(scraper.parse_price("n/a"))

    def test_rating(self):
        for name, value in (("One", 1), ("Two", 2), ("Three", 3), ("Four", 4), ("Five", 5)):
            self.assertEqual(scraper.parse_rating(["star-rating", name]), value)
        self.assertIsNone(scraper.parse_rating(["star-rating"]))
        self.assertIsNone(scraper.parse_rating(None))


class TestDetail(unittest.TestCase):
    def test_description_and_category(self):
        html = (FIXTURES / "detail-1.html").read_text(encoding="utf-8")
        description, category = scraper.parse_detail_page(html)
        self.assertEqual(category, "Poetry")
        self.assertIn("A Light in the Attic", description)
        self.assertGreater(len(description), 100)

    def test_missing_description(self):
        description, category = scraper.parse_detail_page("<html><body></body></html>")
        self.assertEqual(description, "")
        self.assertEqual(category, "")


class TestExport(unittest.TestCase):
    def test_header_is_11_columns(self):
        self.assertEqual(len(export.CSV_HEADER), 11)
        self.assertEqual(export.CSV_HEADER[0], "book_id")
        self.assertEqual(export.CSV_HEADER[-1], "page")

    def test_formula_injection_escaped_only_at_export(self):
        self.assertEqual(export.escape_csv_cell("=SUM(A1)"), "'=SUM(A1)")
        self.assertEqual(export.escape_csv_cell("+1"), "'+1")
        self.assertEqual(export.escape_csv_cell("@x"), "'@x")
        self.assertEqual(export.escape_csv_cell("Normal Title"), "Normal Title")

    def test_csv_roundtrip_with_comma(self):
        rows = [{
            "book_id": "abc123", "title": "Hello, World", "price_gbp": 12.5, "rating": 4,
            "in_stock": True, "category": "Poetry", "product_url": "u", "image_url": "i",
            "image_file": "images/abc123.jpg", "description": 'He said "hi"', "page": 1,
        }]
        parsed = list(csv.reader(io.StringIO(export.rows_to_csv_text(rows))))
        self.assertEqual(parsed[0], export.CSV_HEADER)
        self.assertEqual(parsed[1][1], "Hello, World")
        self.assertEqual(parsed[1][3], "4")
        self.assertEqual(parsed[1][4], "true")
        self.assertEqual(parsed[1][9], 'He said "hi"')

    def test_bom_and_atomic(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "b.csv"
            export.write_csv([{"book_id": "x", "title": "t", "price_gbp": 1, "rating": 1,
                               "in_stock": False, "category": "", "product_url": "", "image_url": "",
                               "image_file": "", "description": "", "page": 1}], path)
            self.assertEqual(path.read_bytes()[:3], b"\xef\xbb\xbf")
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ["b.csv"])

    def test_json_unicode(self):
        rows = [{"book_id": "x", "title": "Café", "price_gbp": 1, "rating": 1, "in_stock": True,
                 "category": "", "product_url": "", "image_url": "", "image_file": "", "description": "", "page": 1}]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "b.json"
            export.write_json(rows, path)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), rows)

    def test_unique_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = export.unique_output_path(Path(tmp), "books", ".csv", "20261124_190000")
            first.write_text("x", encoding="utf-8")
            second = export.unique_output_path(Path(tmp), "books", ".csv", "20261124_190000")
            self.assertEqual(second.name, "books_20261124_190000-1.csv")


if __name__ == "__main__":
    unittest.main(verbosity=2)
