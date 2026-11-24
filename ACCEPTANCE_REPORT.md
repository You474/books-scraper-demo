# 验收报告 · books-scraper-demo

- 时间：2026-11-24
- 目标站：https://books.toscrape.com/（robots.txt 实测 404）
- 依据：[spec.md](spec.md) v1.0 + [acceptance.md](acceptance.md)（AC-01 ~ AC-26）
- **结论：26 / 26 通过**

---

## 1. 环境

| 项 | 值 |
| --- | --- |
| Python | 3.11.4 |
| requests / beautifulsoup4 | 2.34.2 / 4.15.0（钉版） |
| 平台 | Windows 11 + PowerShell |

## 2. 真实站运行（2 页 / 40 本 / 40 张图）

    $ python scraper.py --max-pages 2 --out-dir out
    EXIT=0
    pages=2 rows_seen=40 rows_kept=40 dup=0 images=40 image_skips=0 errors=0 robots=absent stop=max_pages elapsed=67.3s

    out\books_20261124_192814.csv     10684 B
    out\books_20261124_192814.json    19416 B
    out\errors_20261124_192814.jsonl      0 B   （无异常）
    out\images\                      40 张，371.7 KB

首条记录：

    {
      "book_id": "8496bf8dba16",
      "title": "A Light in the Attic",
      "price_gbp": 51.77,
      "rating": 3,
      "in_stock": true,
      "category": "",
      "product_url": "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
      "image_url": "https://books.toscrape.com/media/cache/2c/da/2cdad67c44b002e7ead0cc35693c0e8b.jpg",
      "image_file": "images/8496bf8dba16.jpg",
      "description": "",
      "page": 1
    }

## 3. 自动断言

| 检查 | 结果 |
| --- | --- |
| `tests/verify_output.py`（12 项：BOM / 11 列表头 / CSV=JSON / id 唯一 / title 非空 / price 数值 / rating 1–5 / page 整数 / image_url 非空 / 每条有图 / 图片数 / 无 .tmp） | **12/12 PASS** |
| `python -m unittest discover -s tests` | **27 tests OK，约 109s** |

单测覆盖：列表页解析（真实快照）、title 属性优先、价格/评分/库存归一、详情页简介与分类、CSV 转义与回读、BOM、原子写、同秒不覆盖；
端到端覆盖：翻页跟随 next、403 / 429 / 500、空页有 next / 空尾页、robots 禁止、坏图不丢记录、图片幂等、`--no-images`、`--with-detail`、重复页去重。

## 4. 逐条验收

| 验收项 | 结果 | 依据 |
| --- | --- | --- |
| AC-01 默认 2 页 40 本 | ✅ | 真实站运行 `pages=2 rows_kept=40` |
| AC-02 `--max-pages 1` 20 本 | ✅ | 单测/冒烟：20 行，page 全为 1 |
| AC-03 跟随 next | ✅ | 桩服务 3 页：请求序列 `/ → /page-2.html → /page-3.html` |
| AC-04 末页不越界 | ✅ | 第 3 页无 next 即停，无第 4 页请求 |
| AC-05 空页正常收尾 | ✅ | `emptyend` 场景退出码 0 + `empty_page` warning |
| AC-06 必填非空 / id 唯一 | ✅ | verify_output |
| AC-07 title 取 title 属性 | ✅ | 首行 "A Light in the Attic"（非 "A Light in the ..."） |
| AC-08 价格解析 | ✅ | `£51.77 → 51.77`；`Â£1,234.50 → 1234.5` |
| AC-09 评分映射 1–5 | ✅ | One..Five 全覆盖单测 |
| AC-10 库存归一 | ✅ | "In stock" → true |
| AC-11 `--with-detail` | ✅ | 桩服务：20/20 行有 description，category=Poetry；不加参数时二者为空 |
| AC-12 图片落盘 20 张 | ✅ | 真实站 40 张；桩服务单页 20 张 |
| AC-13 记录与图片关联 | ✅ | verify_output「每条记录都有对应图片」缺失 0 |
| AC-14 坏图不丢记录 | ✅ | `badimage`：20 行保留、`image_skips=20`、`image_file` 空、errors 有 20 条 `image_skipped` |
| AC-15 图片幂等 | ✅ | 同一端口连跑两次：images 仍 20 个，第二次 `images=20` |
| AC-16 `--no-images` | ✅ | 不创建 images 目录，`image_file` 全空 |
| AC-17 同书去重 | ✅ | `duplicate`：`rows_seen=40 rows_kept=20 dup=20` |
| AC-18 403 立即停 | ✅ | 退出码 2，`/page-2.html` 仅 1 次，无 `/page-3.html`，第 1 页 20 行已导出 |
| AC-19 429 立即停 | ✅ | 1 次请求，`retry_after=30`，退出码 2 |
| AC-20 5xx 重试 2 次 | ✅ | `/page-2.html` 共 3 次，3 条 attempt 事件 |
| AC-21 单条坏只跳该条 | ✅ | fixture：缺 title → `parse_missing_field`，其余照常 |
| AC-22 robots 禁止 | ✅ | 请求日志只有 `/robots.txt`，退出码 1 |
| AC-23 CSV 可打开 | ✅（机械） | 表头 11 列、BOM、含逗号书名不拆列；**建议人眼开一次 Excel** |
| AC-24 JSON 合法 | ✅ | 长度 40，每元素 11 键 |
| AC-25 公式注入转义 | ✅ | `=SUM(A1)` → `'=SUM(A1)`（仅 CSV），JSON 不变 |
| AC-26 原子写无残留 | ✅ | verify_output「无 .tmp 残留」 |

## 5. 过程中修复的问题（只改单项）

| # | 问题 | 处置 |
| --- | --- | --- |
| 1 | 图片幂等测试一开始失败（第二次运行图片变 40 张） | **测试写错**：两次运行用了不同随机端口 → URL 不同 → book_id 不同。改为同一服务器连跑两次，代码未动 |
| 2 | 桩服务 shutdown 后 socket 未关闭，输出 ResourceWarning | 测试 finally 里补 `server_close()` |

## 6. 残余风险

1. **AC-23 只做了机械验证**：BOM/表头/转义都对，但没在真实 Excel 里点开过，建议你双击确认一次。
2. **详情页未在真实站全量验证**：`--with-detail` 只在 1 页（20 本）桩服务 + 1 次真实站 20 本上跑过，50 页全量会有 1000 次详情请求，未做。
3. **选择器绑定该站**：站点改版即失效，需同步改 `parse_list_page`。
4. **图片不校验完整性**：只校验 Content-Type 与大小，不校验 JPEG 是否能解码；坏文件会以正常文件名保存。

---

## 7. 推送上线

- 仓库：https://github.com/You474/books-scraper-demo （新建空仓库，Public）
- 首次推送：`* [new branch] main -> main`，本地 `9ac3e11` = 远端 HEAD
- 远端文件数：**18**（源码 2 + 测试 5 + fixtures 3 + 文档 7 + 配置 1）

    $ git rev-parse HEAD         9ac3e1104665f82c7848d3e5044f96203067fd5a
    $ git rev-parse origin/main  9ac3e1104665f82c7848d3e5044f96203067fd5a

- 未入库（`.gitignore` 生效）：`out/`（40 张封面图 + 导出文件）、`.test-out/`（测试临时目录）、`.venv/`、`__pycache__/`、`tmp*/`

