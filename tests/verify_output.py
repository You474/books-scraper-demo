#!/usr/bin/env python3
"""校验一次运行的导出结果。

python tests/verify_output.py out\books_x.csv out\books_x.json out\images
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

HEADER = ["book_id", "title", "price_gbp", "rating", "in_stock", "category",
          "product_url", "image_url", "image_file", "description", "page"]


def main() -> int:
    csv_path, json_path = Path(sys.argv[1]), Path(sys.argv[2])
    images_dir = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    checks: list[tuple[str, bool, str]] = []

    raw = csv_path.read_bytes()
    checks.append(("CSV 带 utf-8-sig BOM", raw[:3] == b"\xef\xbb\xbf", raw[:3].hex()))
    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    records = json.loads(json_path.read_text(encoding="utf-8"))

    checks.append(("表头 11 列一致", rows[0] == HEADER, str(len(rows[0]))))
    checks.append(("CSV 行数 == JSON 条数", len(rows) - 1 == len(records), f"{len(rows)-1}/{len(records)}"))
    checks.append(("book_id 唯一", len({r["book_id"] for r in records}) == len(records), "-"))
    checks.append(("title 全部非空", all(r["title"].strip() for r in records), "-"))
    checks.append(("price 为数值", all(isinstance(r["price_gbp"], (int, float)) for r in records), "-"))
    checks.append(("rating 在 1..5", all(1 <= r["rating"] <= 5 for r in records), "-"))
    checks.append(("page 为整数", all(isinstance(r["page"], int) for r in records), "-"))
    checks.append(("image_url 非空", all(r["image_url"] for r in records), "-"))

    if images_dir is not None:
        missing = [r["image_file"] for r in records if not r["image_file"] or not (images_dir.parent / r["image_file"]).exists()]
        checks.append(("每条记录都有对应图片", not missing, f"缺失 {len(missing)}"))
        checks.append(("images 数量 >= 记录数", len(list(images_dir.glob("*"))) >= len(records), str(len(list(images_dir.glob("*"))))))
    checks.append(("无 .tmp 残留", not list(csv_path.parent.glob("*.tmp")), "-"))

    failed = [n for n, ok, _ in checks if not ok]
    for name, ok, detail in checks:
        print(("PASS  " if ok else "FAIL  ") + name + ("  (" + detail + ")" if detail != "-" else ""))
    print(f"\n{len(checks) - len(failed)}/{len(checks)} 通过")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
