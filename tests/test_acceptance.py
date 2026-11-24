#!/usr/bin/env python3
"""端到端验收：起桩服务跑 scraper.py，断言退出码、请求序列、文件与图片。"""

from __future__ import annotations

import csv
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fake_server  # noqa: E402


TEST_ROOT = ROOT / ".test-out"


def run_scenario(scenario: str, max_pages: str = "2", out_dir: str | None = None, *extra: str):
    httpd, _thread, port = fake_server.serve(0, scenario)
    TEST_ROOT.mkdir(exist_ok=True)
    tmp = out_dir or tempfile.mkdtemp(dir=str(TEST_ROOT), prefix="run_")
    try:
        proc = subprocess.run(
            [
                sys.executable, "scraper.py",
                "--base-url", f"http://127.0.0.1:{port}/",
                "--delay", "0.2",
                "--out-dir", tmp,
                "--max-pages", max_pages,
                *extra,
            ],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", timeout=240,
        )
    finally:
        httpd.shutdown()
        httpd.server_close()
    files = {p.name: p for p in Path(tmp).iterdir() if p.is_file()}
    contents = {}
    for name, path in files.items():
        contents[name] = path.read_text(encoding="utf-8-sig" if name.endswith(".csv") else "utf-8")
    return proc, Path(tmp), contents, list(httpd.state["log"])


def csv_rows(text: str):
    return list(csv.reader(io.StringIO(text)))


def rows_json(contents):
    for name, text in contents.items():
        if name.endswith(".json"):
            return json.loads(text)
    return []


def errors_of(contents):
    for name, text in contents.items():
        if name.endswith(".jsonl"):
            return [json.loads(line) for line in text.splitlines() if line.strip()]
    return []


class TestHappyPath(unittest.TestCase):
    def test_two_pages_with_images(self):
        proc, out, contents, log = run_scenario("ok", "2")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("pages=2", proc.stderr)
        self.assertIn("rows_kept=40", proc.stderr)
        self.assertIn("images=40", proc.stderr)                     # AC-12
        self.assertIn("robots=present", proc.stderr)
        images = list((out / "images").glob("*"))
        self.assertEqual(len(images), 40)                            # AC-12
        self.assertTrue(all(p.stat().st_size > 0 for p in images))
        rows = csv_rows([t for n, t in contents.items() if n.endswith(".csv")][0])
        self.assertEqual(rows[0], ["book_id", "title", "price_gbp", "rating", "in_stock",
                                   "category", "product_url", "image_url", "image_file", "description", "page"])
        self.assertEqual(len(rows) - 1, 40)                          # AC-01
        records = rows_json(contents)
        self.assertEqual(len(records), 40)
        self.assertEqual(len(records[0]), 11)                        # AC-24
        # 每条 image_file 指向的文件都存在（AC-13）
        for record in records:
            self.assertTrue(record["image_file"])
            self.assertTrue((out / record["image_file"]).exists())

    def test_pagination_follows_next(self):
        proc, _out, _contents, log = run_scenario("ok", "3")
        pages = [e["path"] for e in log if e["path"] in ("/", "/page-2.html", "/page-3.html")]
        self.assertEqual(pages, ["/", "/page-2.html", "/page-3.html"])   # AC-03
        self.assertEqual(proc.returncode, 0)

    def test_no_images_flag(self):
        proc, out, contents, _log = run_scenario("ok", "1", None, "--no-images")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse((out / "images").exists())                  # AC-16
        self.assertTrue(all(r["image_file"] == "" for r in rows_json(contents)))

    def test_with_detail(self):
        proc, _out, contents, _log = run_scenario("ok", "1", None, "--no-images", "--with-detail")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        records = rows_json(contents)
        self.assertTrue(all(r["description"] for r in records))       # AC-11
        self.assertTrue(all(r["category"] == "Poetry" for r in records))


class TestDedup(unittest.TestCase):
    def test_duplicate_pages_collapse(self):
        proc, _out, contents, _log = run_scenario("duplicate", "2", None, "--no-images")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("rows_seen=40", proc.stderr)
        self.assertIn("rows_kept=20", proc.stderr)
        self.assertIn("dup=20", proc.stderr)                          # AC-17


class TestImageFailures(unittest.TestCase):
    def test_bad_image_keeps_row(self):
        proc, out, contents, _log = run_scenario("badimage", "1")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("image_skips=20", proc.stderr)                  # AC-14
        records = rows_json(contents)
        self.assertEqual(len(records), 20)
        self.assertTrue(all(r["image_file"] == "" for r in records))
        reasons = [e["reason"] for e in errors_of(contents)]
        self.assertEqual(reasons.count("image_skipped"), 20)
        self.assertFalse((out / "images").exists() and any((out / "images").iterdir()))

    def test_idempotent_download(self):
        """同一端口 = 同一批 URL = 同一批 book_id，第二次必须跳过已存在的图片。"""
        httpd, _thread, port = fake_server.serve(0, "ok")
        TEST_ROOT.mkdir(exist_ok=True)
        out_dir = tempfile.mkdtemp(dir=str(TEST_ROOT), prefix="idem_")
        try:
            def run_once():
                return subprocess.run(
                    [sys.executable, "scraper.py", "--base-url", f"http://127.0.0.1:{port}/",
                     "--delay", "0.2", "--out-dir", out_dir, "--max-pages", "1"],
                    cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", timeout=240,
                )

            first = run_once()
            self.assertEqual(first.returncode, 0, first.stderr)
            images_dir = Path(out_dir) / "images"
            self.assertEqual(len(list(images_dir.glob("*"))), 20)
            second = run_once()
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(len(list(images_dir.glob("*"))), 20)     # AC-15 不重复下载
            self.assertIn("images=20", second.stderr)
        finally:
            httpd.shutdown()
            httpd.server_close()


class TestForbidden(unittest.TestCase):
    def test_403_stops(self):
        proc, _out, contents, log = run_scenario("403", "3")
        paths = [e["path"] for e in log]
        self.assertEqual(proc.returncode, 2, proc.stderr)             # AC-18
        self.assertIn("/page-2.html", paths)
        self.assertNotIn("/page-3.html", paths)
        self.assertEqual(paths.count("/page-2.html"), 1)
        self.assertTrue(any(e["status"] == 403 for e in errors_of(contents)))
        csv_files = [n for n in contents if n.endswith(".csv")]
        self.assertEqual(len(csv_rows(contents[csv_files[0]])) - 1, 20)

    def test_429_stops(self):
        proc, _out, contents, log = run_scenario("429", "3")
        paths = [e["path"] for e in log]
        self.assertEqual(proc.returncode, 2, proc.stderr)             # AC-19
        self.assertEqual(paths.count("/page-2.html"), 1)
        hit = [e for e in errors_of(contents) if e["reason"] == "http_rate_limited"]
        self.assertIn("retry_after=30", hit[0]["detail"])

    def test_500_retries_twice(self):
        proc, _out, contents, log = run_scenario("500", "3")
        paths = [e["path"] for e in log]
        self.assertEqual(proc.returncode, 2, proc.stderr)             # AC-20
        self.assertEqual(paths.count("/page-2.html"), 3)
        self.assertEqual(len([e for e in errors_of(contents) if e["reason"] == "http_server_error"]), 3)


class TestEmptyAndRobots(unittest.TestCase):
    def test_empty_end_is_normal(self):
        proc, _out, contents, _log = run_scenario("emptyend", "3", None, "--no-images")
        self.assertEqual(proc.returncode, 0, proc.stderr)             # AC-05
        self.assertIn("empty_page", [e["reason"] for e in errors_of(contents)])

    def test_empty_with_next_is_error(self):
        proc, _out, contents, _log = run_scenario("emptynext", "3", None, "--no-images")
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("parse_empty_page_with_next", [e["reason"] for e in errors_of(contents)])

    def test_robots_disallow(self):
        proc, _out, _contents, log = run_scenario("disallow", "2", None, "--no-images")
        self.assertEqual(proc.returncode, 1, proc.stderr)             # AC-22
        self.assertEqual([e["path"] for e in log], ["/robots.txt"])

    def test_no_rows_produces_no_csv(self):
        proc, _out, contents, _log = run_scenario("noquotes", "1", None, "--no-images")
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertEqual([n for n in contents if n.endswith((".csv", ".json"))], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
