#!/usr/bin/env python3
"""导出层：CSV / JSON / JSONL（books demo 版，11 列）。

- 采集/解析层不改数据；CSV 公式注入（CWE-1236）只在这里转义。
- 原子写：.tmp -> os.replace。
"""

from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path

CSV_HEADER = [
    "book_id",
    "title",
    "price_gbp",
    "rating",
    "in_stock",
    "category",
    "product_url",
    "image_url",
    "image_file",
    "description",
    "page",
]

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def escape_csv_cell(value: str) -> str:
    if value and value[0] in FORMULA_PREFIXES:
        return "'" + value
    return value


def _atomic_write_text(path: Path, data: str, encoding: str, newline: str | None = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "w", encoding=encoding, newline=newline) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise
    return path


def rows_to_csv_text(rows: list[dict]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(CSV_HEADER)
    for row in rows:
        writer.writerow(
            [
                escape_csv_cell(str(row.get("book_id", ""))),
                escape_csv_cell(str(row.get("title", ""))),
                row.get("price_gbp", ""),
                row.get("rating", ""),
                "true" if row.get("in_stock") else "false",
                escape_csv_cell(str(row.get("category", ""))),
                escape_csv_cell(str(row.get("product_url", ""))),
                escape_csv_cell(str(row.get("image_url", ""))),
                escape_csv_cell(str(row.get("image_file", ""))),
                escape_csv_cell(str(row.get("description", ""))),
                row.get("page", ""),
            ]
        )
    return buffer.getvalue()


def write_csv(rows: list[dict], path: Path) -> Path:
    return _atomic_write_text(path, rows_to_csv_text(rows), encoding="utf-8-sig", newline="")


def write_json(rows: list[dict], path: Path) -> Path:
    return _atomic_write_text(path, json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_errors(events: list[dict], path: Path) -> Path:
    data = "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events)
    return _atomic_write_text(path, data, encoding="utf-8")


def unique_output_path(out_dir: Path, stem: str, suffix: str, stamp: str) -> Path:
    out_dir = Path(out_dir)
    candidate = out_dir / f"{stem}_{stamp}{suffix}"
    index = 1
    while candidate.exists():
        candidate = out_dir / f"{stem}_{stamp}-{index}{suffix}"
        index += 1
    return candidate
