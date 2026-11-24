#!/usr/bin/env python3
"""图文采集 Demo：books.toscrape.com（列表页 → 字段 + 封面图，可选详情页）。

合规：只采公开页面，robots 三态检查，串行限速，403/429 立即停止。
规格见 spec.md，验收见 acceptance.md。
"""

from __future__ import annotations

import argparse
import hashlib
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

import export as exporter

DEFAULT_BASE_URL = "https://books.toscrape.com/"
USER_AGENT = "books-scraper-demo/1.0 (+educational demo)"
TIMEOUT_SECONDS = 10
MIN_DELAY = 0.2
DEFAULT_DELAY = 1.0
JITTER_SECONDS = 0.3
RETRY_BACKOFF = (2, 4)
IMAGE_MAX_BYTES = 5 * 1024 * 1024
IMAGE_EXT_BY_TYPE = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
RATING_MAP = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}

EXIT_OK, EXIT_PRECONDITION, EXIT_PARTIAL = 0, 1, 2


def clean(value: str | None) -> str:
    return " ".join((value or "").split())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def event(page, url, status, reason, detail=""):
    return {"ts": now_iso(), "page": page, "url": url, "status": status, "reason": reason, "detail": detail}


def make_book_id(product_url: str) -> str:
    return hashlib.sha256(product_url.encode("utf-8")).hexdigest()[:12]


def parse_price(text: str) -> float | None:
    digits = re.sub(r"[^0-9.]", "", text or "")
    try:
        return round(float(digits), 2)
    except (TypeError, ValueError):
        return None


def parse_rating(classes) -> int | None:
    for name in classes or []:
        if name in RATING_MAP:
            return RATING_MAP[name]
    return None


def parse_list_page(html: str, page: int, page_url: str) -> tuple[list[dict], list[dict], str | None]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []
    problems: list[dict] = []

    for index, card in enumerate(soup.select("article.product_pod"), start=1):
        link = card.select_one("h3 a")
        href = link.get("href") if link else None
        title = clean(link.get("title") or link.get_text()) if link else ""
        if not title or not href:
            problems.append(event(page, page_url, None, "parse_missing_field", f"index={index} 无标题或无链接"))
            continue

        product_url = urljoin(page_url, href)
        price_el = card.select_one("p.price_color")
        price = parse_price(price_el.get_text() if price_el else "")
        if price is None:
            problems.append(event(page, product_url, None, "parse_bad_price", "价格解析失败"))
            continue

        rating_el = card.select_one("p.star-rating")
        rating = parse_rating(rating_el.get("class") if rating_el else None)
        if rating is None:
            problems.append(event(page, product_url, None, "parse_bad_rating", "评分无法识别"))
            continue

        availability_el = card.select_one("p.instock.availability")
        in_stock = "in stock" in clean(availability_el.get_text()).lower() if availability_el else False

        image_el = card.select_one("div.image_container img")
        image_src = image_el.get("src") if image_el else None
        image_url = urljoin(page_url, image_src) if image_src else ""

        rows.append(
            {
                "book_id": make_book_id(product_url),
                "title": title,
                "price_gbp": price,
                "rating": rating,
                "in_stock": in_stock,
                "category": "",
                "product_url": product_url,
                "image_url": image_url,
                "image_file": "",
                "description": "",
                "page": page,
            }
        )

    next_el = soup.select_one("ul.pager li.next a")
    next_href = next_el["href"] if next_el and next_el.get("href") else None
    return rows, problems, next_href


def parse_detail_page(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    description = ""
    header = soup.select_one("#product_description")
    if header is not None:
        para = header.find_next_sibling("p")
        description = clean(para.get_text()) if para else ""
    category = ""
    crumbs = soup.select("ul.breadcrumb li a")
    if len(crumbs) >= 3:
        category = clean(crumbs[2].get_text())
    return description, category


def load_robots(session, base_url, errors):
    robots_url = urljoin(base_url, "/robots.txt")
    try:
        response = session.get(robots_url, timeout=TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        errors.append(event(None, robots_url, None, "robots_unknown", str(exc)))
        return "unknown", None
    if response.status_code in (404, 410):
        return "absent", None
    if response.status_code != 200:
        errors.append(event(None, robots_url, response.status_code, "robots_unknown", "非 200/404"))
        return "unknown", None
    parser = RobotFileParser()
    parser.parse(response.text.splitlines())
    return "present", parser


def fetch(session, url, page, errors):
    attempts = len(RETRY_BACKOFF) + 1
    for attempt in range(attempts):
        try:
            response = session.get(url, timeout=TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT})
        except requests.Timeout as exc:
            errors.append(event(page, url, None, "timeout", f"attempt={attempt + 1} {exc}"))
        except requests.RequestException as exc:
            errors.append(event(page, url, None, "network_error", f"attempt={attempt + 1} {exc}"))
        else:
            if response.status_code < 500:
                return response
            errors.append(event(page, url, response.status_code, "http_server_error", f"attempt={attempt + 1}"))
        if attempt < len(RETRY_BACKOFF):
            time.sleep(RETRY_BACKOFF[attempt])
    return None


def download_image(session, image_url, book_id, images_dir: Path, page, errors) -> str:
    if not image_url:
        errors.append(event(page, "", None, "image_skipped", "无图片地址"))
        return ""

    suffix = Path(image_url.split("?")[0]).suffix.lower()
    existing = list(images_dir.glob(f"{book_id}.*")) if images_dir.exists() else []
    if existing:
        return f"images/{existing[0].name}"

    try:
        response = session.get(image_url, timeout=TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT})
    except requests.RequestException as exc:
        errors.append(event(page, image_url, None, "image_skipped", f"请求失败 {exc}"))
        return ""

    if response.status_code != 200:
        errors.append(event(page, image_url, response.status_code, "image_skipped", "HTTP 非 200"))
        return ""

    content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    if not content_type.startswith("image/"):
        errors.append(event(page, image_url, response.status_code, "image_skipped", f"非图片类型 {content_type}"))
        return ""

    payload = response.content
    if not payload:
        errors.append(event(page, image_url, response.status_code, "image_skipped", "空文件"))
        return ""
    if len(payload) > IMAGE_MAX_BYTES:
        errors.append(event(page, image_url, response.status_code, "image_too_large", f"{len(payload)} bytes"))
        return ""

    ext = IMAGE_EXT_BY_TYPE.get(content_type, suffix or ".bin")
    images_dir.mkdir(parents=True, exist_ok=True)
    target = images_dir / f"{book_id}{ext}"
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_bytes(payload)
    tmp.replace(target)
    return f"images/{target.name}"


def crawl(session, base_url, max_pages, delay, with_detail, with_images, out_dir, errors, stats):
    rows: list[dict] = []
    seen: set[str] = set()
    visited: set[str] = set()
    images_dir = Path(out_dir) / "images"
    url = base_url
    stop_reason = "max_pages"

    while stats["pages"] < max_pages:
        if url in visited:
            errors.append(event(stats["pages"] + 1, url, None, "pagination_loop", "下一跳 URL 已访问"))
            stop_reason = "pagination_loop"
            break
        visited.add(url)
        stats["pages"] += 1
        page_no = stats["pages"]

        response = fetch(session, url, page_no, errors)
        if response is None:
            stop_reason = "fetch_failed"
            break

        status = response.status_code
        if status == 403:
            errors.append(event(page_no, url, 403, "http_forbidden", "403 立即停止"))
            stop_reason = "http_forbidden"
            break
        if status == 429:
            errors.append(event(page_no, url, 429, "http_rate_limited",
                                f"retry_after={response.headers.get('Retry-After', '')}"))
            stop_reason = "http_rate_limited"
            break
        if status != 200:
            errors.append(event(page_no, url, status, "http_error", "非 200"))
            stop_reason = "http_error"
            break

        page_rows, problems, next_href = parse_list_page(response.text, page_no, response.url)
        errors.extend(problems)
        stats["rows_seen"] += len(page_rows)

        for row in page_rows:
            if row["book_id"] in seen:
                stats["rows_duplicated"] += 1
                continue
            seen.add(row["book_id"])

            if with_detail:
                time.sleep(delay + random.uniform(0, JITTER_SECONDS))
                detail = fetch(session, row["product_url"], page_no, errors)
                if detail is not None and detail.status_code == 200:
                    row["description"], row["category"] = parse_detail_page(detail.text)
                elif detail is not None:
                    errors.append(event(page_no, row["product_url"], detail.status_code, "detail_error", "详情页非 200"))

            if with_images:
                time.sleep(delay + random.uniform(0, JITTER_SECONDS))
                row["image_file"] = download_image(session, row["image_url"], row["book_id"], images_dir, page_no, errors)
                if row["image_file"]:
                    stats["images"] += 1
                else:
                    stats["image_skips"] += 1

            rows.append(row)

        next_url = urljoin(response.url, next_href) if next_href else None

        if not page_rows:
            if next_url:
                errors.append(event(page_no, url, status, "parse_empty_page_with_next", "有 next 但 0 条"))
                stop_reason = "parse_empty_page_with_next"
                break
            if rows:
                errors.append(event(page_no, url, status, "empty_page", "越界空页，正常收尾"))
                stop_reason = "empty_page"
                break
            stop_reason = "no_rows"
            break

        if not next_url:
            stop_reason = "no_next"
            break
        url = next_url
        time.sleep(delay + random.uniform(0, JITTER_SECONDS))

    return rows, stop_reason


def build_parser():
    parser = argparse.ArgumentParser(description="图文采集 demo：books.toscrape.com")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--max-pages", type=int, default=2)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    parser.add_argument("--out-dir", default="out")
    parser.add_argument("--format", choices=("both", "csv", "json"), default="both")
    parser.add_argument("--no-images", action="store_true", help="不下载封面图")
    parser.add_argument("--with-detail", action="store_true", help="额外抓详情页（简介 + 分类）")
    return parser


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    args = build_parser().parse_args(argv)
    if args.max_pages < 1:
        print("[error] --max-pages 必须 >= 1", file=sys.stderr)
        return EXIT_PRECONDITION
    if args.delay < MIN_DELAY:
        print(f"[error] --delay 不能小于 {MIN_DELAY}", file=sys.stderr)
        return EXIT_PRECONDITION
    if not args.base_url.startswith(("http://", "https://")):
        print("[error] --base-url 需以 http(s):// 开头", file=sys.stderr)
        return EXIT_PRECONDITION

    base_url = args.base_url.rstrip("/") + "/"
    out_dir = Path(args.out_dir)
    errors: list[dict] = []
    stats = {"pages": 0, "rows_seen": 0, "images": 0, "image_skips": 0, "rows_duplicated": 0}
    started = time.time()

    session = requests.Session()
    robots_state, robots_parser = load_robots(session, base_url, errors)
    if robots_state == "present" and robots_parser is not None and not robots_parser.can_fetch(USER_AGENT, base_url):
        errors.append(event(None, urljoin(base_url, "robots.txt"), 200, "robots_disallow", "robots.txt 禁止"))
        try:
            exporter.write_errors(errors, exporter.unique_output_path(out_dir, "errors", ".jsonl", time.strftime("%Y%m%d_%H%M%S")))
        except OSError:
            pass
        print("[error] robots.txt 禁止抓取，未发起页面请求", file=sys.stderr)
        return EXIT_PRECONDITION

    delay = max(args.delay, MIN_DELAY)
    if robots_state == "unknown":
        delay = max(delay, 2.0)
        print("[warn] robots.txt 无法确认，间隔提升到 2s", file=sys.stderr)

    rows, stop_reason = crawl(session, base_url, args.max_pages, delay,
                              args.with_detail, not args.no_images, out_dir, errors, stats)
    elapsed = time.time() - started
    stamp = time.strftime("%Y%m%d_%H%M%S")

    csv_path = json_path = None
    try:
        if not rows:
            errors.append(event(None, base_url, None, "no_rows", "一条都没采到，不产出空文件"))
        else:
            if args.format in ("both", "csv"):
                csv_path = exporter.write_csv(rows, exporter.unique_output_path(out_dir, "books", ".csv", stamp))
            if args.format in ("both", "json"):
                json_path = exporter.write_json(rows, exporter.unique_output_path(out_dir, "books", ".json", stamp))
        errors_path = exporter.write_errors(errors, exporter.unique_output_path(out_dir, "errors", ".jsonl", stamp))
    except OSError as exc:
        print(f"[error] 写入失败: {exc}", file=sys.stderr)
        return EXIT_PRECONDITION

    normal_end = {"no_next", "max_pages", "empty_page"}
    exit_code = EXIT_OK if stop_reason in normal_end and rows else EXIT_PARTIAL

    print(
        f"pages={stats['pages']} rows_seen={stats['rows_seen']} rows_kept={len(rows)} dup={stats['rows_duplicated']} "
        f"images={stats['images']} image_skips={stats['image_skips']} errors={len(errors)} "
        f"robots={robots_state} stop={stop_reason} elapsed={elapsed:.1f}s",
        file=sys.stderr,
    )
    if csv_path:
        print(f"csv={csv_path}", file=sys.stderr)
    if json_path:
        print(f"json={json_path}", file=sys.stderr)
    print(f"errors_log={errors_path}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
