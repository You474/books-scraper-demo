#!/usr/bin/env python3
"""stdlib 桩服务：列表页 / 详情页 / 图片，覆盖 403、429、500、空页、robots、坏图、重复页。

单独运行：python tests/fake_server.py 8010 --scenario 429
测试里：httpd, thread, port = serve(0, "ok")
"""

from __future__ import annotations

import argparse
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SCENARIOS = (
    "ok",
    "403",
    "429",
    "500",
    "emptynext",
    "emptyend",
    "noquotes",
    "disallow",
    "absent",
    "duplicate",
    "badimage",
)

TOTAL_PAGES = 3
PER_PAGE = 20
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"x" * 200


def book_html(page: int, index: int, book_key: str | None = None) -> str:
    key = book_key or f"{page}-{index}"
    slug = f"book-{key}"
    return (
        '<article class="product_pod">'
        '<div class="image_container">'
        f'<a href="{slug}.html"><img src="media/{slug}.jpg" alt="Book {key}" class="thumbnail"></a>'
        "</div>"
        '<p class="star-rating Three"><i class="icon-star"></i><i class="icon-star"></i><i class="icon-star"></i></p>'
        f'<h3><a href="{slug}.html" title="Book {key} Full Title">Book {key} ...</a></h3>'
        '<div class="product_price">'
        f'<p class="price_color">£{10 + index}.99</p>'
        '<p class="instock availability"><i class="icon-ok"></i>In stock</p>'
        "</div></article>"
    )


def list_page(page: int, next_page: int | None, cards: list[str]) -> str:
    pager = '<ul class="pager">'
    if next_page:
        pager += f'<li class="next"><a href="page-{next_page}.html">next</a></li>'
    pager += "</ul>"
    return (
        "<html><head><title>Books</title></head><body>"
        + "".join(cards)
        + pager
        + "</body></html>"
    )


def detail_page(key: str) -> str:
    return (
        "<html><body>"
        '<ul class="breadcrumb"><li><a href="/">Home</a></li><li><a href="/catalogue/">Books</a></li>'
        '<li><a href="/category/poetry_23/index.html">Poetry</a></li></ul>'
        '<div id="product_description" class="sub-header"><h2>Product Description</h2></div>'
        f"<p>Description for book {key}.</p>"
        "</body></html>"
    )


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, status: int, body: bytes, content_type: str = "text/html; charset=utf-8", extra=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        state = self.server.state
        path = self.path.split("?")[0]
        state["log"].append({"path": path, "ua": self.headers.get("User-Agent", ""), "ts": time.time()})
        scenario = state["scenario"]

        if path == "/_log":
            self._send(200, json.dumps(state["log"]).encode(), "application/json")
            return

        if path == "/robots.txt":
            if scenario == "absent":
                self._send(404, b"not found", "text/plain")
            elif scenario == "disallow":
                self._send(200, b"User-agent: *\nDisallow: /\n", "text/plain")
            else:
                self._send(200, b"User-agent: *\nAllow: /\n", "text/plain")
            return

        if path.startswith("/media/"):
            if scenario == "badimage":
                self._send(404, b"not found", "text/plain")
            else:
                self._send(200, JPEG, "image/jpeg")
            return

        m = re.match(r"^/book-(.+)\.html$", path)
        if m:
            self._send(200, detail_page(m.group(1)).encode(), "text/html; charset=utf-8")
            return

        if path in ("/", ""):
            page = 1
        else:
            m = re.match(r"^/page-(\d+)\.html$", path)
            page = int(m.group(1)) if m else 0
        if page == 0:
            self._send(404, b"not found", "text/plain")
            return

        if page == 2 and scenario == "403":
            self._send(403, b"<h1>403</h1>")
            return
        if page == 2 and scenario == "429":
            self._send(429, b"<h1>429</h1>", extra={"Retry-After": "30"})
            return
        if page == 2 and scenario == "500":
            self._send(500, b"<h1>500</h1>")
            return
        if page == 2 and scenario == "emptynext":
            self._send(200, list_page(2, 3, []).encode())
            return
        if page == 2 and scenario == "emptyend":
            self._send(200, list_page(2, None, []).encode())
            return
        if page == 1 and scenario == "noquotes":
            self._send(200, list_page(1, None, []).encode())
            return

        if scenario == "duplicate":
            cards = [book_html(page, i, book_key=str(i)) for i in range(1, PER_PAGE + 1)]
        else:
            cards = [book_html(page, i) for i in range(1, PER_PAGE + 1)]

        next_page = page + 1 if page < TOTAL_PAGES else None
        self._send(200, list_page(page, next_page, cards).encode())


def serve(port: int = 0, scenario: str = "ok"):
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.state = {"scenario": scenario, "log": []}
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, thread, httpd.server_address[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("port", nargs="?", type=int, default=8010)
    parser.add_argument("--scenario", default="ok", choices=SCENARIOS)
    args = parser.parse_args()
    httpd, _t, port = serve(args.port, args.scenario)
    print(f"fake_server on http://127.0.0.1:{port}/ scenario={args.scenario}", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        httpd.shutdown()


if __name__ == "__main__":
    main()
