# Books Scraper Demo — Spec（v1.0，图文采集）

- 目标站点：https://books.toscrape.com/（Zyte 的爬虫教学沙盒，与 quotes.toscrape.com 同源系列）
- 形态：命令行采集器，Python 3.9+，依赖 `requests` + `beautifulsoup4`（html.parser）
- 特点：**图文混采** —— 文本字段 + 封面图下载落盘，图片与记录通过 `book_id` 关联
- 规模：默认只跑 2 页（40 本），上限 50 页 / 1000 本

---

## 1. 站点事实（实测 2026-11-24）

| 项 | 结果 | 对设计的影响 |
| --- | --- | --- |
| robots.txt | **404**（未发布） | 记 `robots:absent` 后继续，保持保守限速 |
| 列表页 | 每页 20 个 `article.product_pod` | 分页基数 20 |
| 分页 | `ul.pager li.next a[href]` → `catalogue/page-2.html`；共 **50 页** | 跟随 next，不猜页码 |
| 封面图 | `div.image_container img.thumbnail`，相对路径 `media/cache/...jpg` | 需 `urljoin` 成绝对地址再下载 |
| 标题 | `h3 a[title]`（完整标题在 title 属性，链接文字被截断为 "A Light in the ..."） | 必须取 `title` 属性，不能取文本 |
| 价格 | `p.price_color` → `£51.77` | 拆成数值 `price_gbp` |
| 评分 | `p.star-rating` 的第二个 class（One…Five） | 映射为 1–5 |
| 库存 | `p.instock.availability` 文本 "In stock" | 归一为布尔 |
| 详情页 | `#product_description + p` 是简介；`ul.breadcrumb` 有分类 | 可选抓取（`--with-detail`），默认关闭以控制请求量 |

---

## 2. 字段

| 字段 | 类型 | 来源 | 规则 |
| --- | --- | --- | --- |
| `book_id` | str | 派生 | 商品页 URL 的 sha256 前 12 位；图片文件名与去重键都用它 |
| `title` | str | `h3 a[title]` | 去空白；**取 title 属性**（页面文字被截断） |
| `price_gbp` | float | `p.price_color` | 去掉 £ 与千分位，保留 2 位小数；解析失败记 `parse_bad_price` 并跳过该条 |
| `rating` | int 1–5 | `p.star-rating` class | One..Five → 1..5；无法识别记 `parse_bad_rating` 跳过 |
| `in_stock` | bool | `p.instock.availability` | 文本含 "In stock" 为真 |
| `category` | str | 详情页 `ul.breadcrumb li:nth-child(3) a` | 未开 `--with-detail` 时为空串 |
| `product_url` | str | `h3 a[href]` | 相对 → 绝对 |
| `image_url` | str | `img.thumbnail[src]` | 相对 → 绝对 |
| `image_file` | str | 下载结果 | 成功为 `images/<book_id>.jpg`，失败为空串（记录不丢） |
| `description` | str | 详情页 `#product_description ~ p` | 未开 `--with-detail` 时为空串 |
| `page` | int | 采集器 | 1 起始的列表页码 |

CSV 列顺序固定：`book_id,title,price_gbp,rating,in_stock,category,product_url,image_url,image_file,description,page`

---

## 3. 图片下载

- 只下载列表页出现过的封面图；`--no-images` 可整体关闭。
- 目标路径：`{out-dir}/images/<book_id><ext>`，ext 由 Content-Type 推断（jpg/png/webp/gif），拿不到则用 URL 后缀。
- 校验：HTTP 200 + Content-Type 以 `image/` 开头 + 大小 > 0；任一不满足记 `image_skipped`，**该条记录仍保留**（`image_file` 为空）。
- 已存在同名文件则跳过（幂等，支持重跑）。
- 单张上限 5 MB，超限丢弃并记 `image_too_large`。
- 图片请求与页面请求共用同一限速与 UA。

---

## 4. 翻页与停止（与 Quote Demo 同构）

| 序 | 条件 | 处理 | 退出码 |
| --- | --- | --- | --- |
| S1 | 403 | 立即停止，不重试 | 2 |
| S2 | 429 | 立即停止，记录 `Retry-After` | 2 |
| S3 | 其它 4xx | 停止 | 2 |
| S4 | 5xx / 超时 / 网络错误 | 重试 2 次（2s、4s）后停止 | 2 |
| S5 | 0 条且无 next | 已采到数据 → 正常收尾；一条没有 → `no_rows` | 0 / 2 |
| S6 | 0 条但有 next | `parse_empty_page_with_next` 停止 | 2 |
| S7 | 无 next | 正常结束 | 0 |
| S8 | 达 `--max-pages` | 正常结束 | 0 |
| S9 | 下一跳已访问 | `pagination_loop` 停止 | 2 |

---

## 5. 去重与导出

- 去重键：`book_id`（商品页 URL 指纹），保留首次出现。
- 导出：CSV（utf-8-sig，含公式注入转义） + JSON（`ensure_ascii=False`） + `errors_*.jsonl`。
- 原子写（`.tmp` → rename），同秒重跑加 `-1` 后缀。
- 素材体积：默认 2 页 ≈ 40 张图（约 0.5–1 MB），全部 50 页约 20 MB。

---

## 6. 合规

- 只采公开页面；robots 三态处理（present/absent/unknown），Disallow 直接退出。
- UA：`books-scraper-demo/1.0 (+educational demo)`；串行、默认 1.0s 间隔（下限 0.2s）。
- 不登录、不绕验证码、不并发、不抓用户数据；默认只跑 2 页，避免对站点造成压力。
- 图片版权归原出版社/作者，仅本地留存，不二次分发。

---

## 7. 命令行

    python scraper.py                       # 默认 2 页 / 40 本 + 封面图
    python scraper.py --max-pages 5         # 5 页 / 100 本
    python scraper.py --no-images           # 只采文本，不下载图片
    python scraper.py --with-detail         # 额外抓详情页（简介 + 分类），请求数翻倍
    python scraper.py --out-dir D:\data\books --delay 2.0

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--base-url` | books.toscrape.com | 可指向本地桩服务 |
| `--max-pages` | 2 | 上限 50 |
| `--delay` | 1.0 | 相邻请求间隔，下限 0.2 |
| `--out-dir` | out | 输出目录 |
| `--format` | both | both / csv / json |
| `--no-images` | 关 | 关闭图片下载 |
| `--with-detail` | 关 | 抓详情页补简介与分类 |

---

## 8. 文件结构

    books-scraper-demo/
    ├── scraper.py            # 列表页翻页、字段解析、图片下载、去重、编排
    ├── export.py             # CSV/JSON/JSONL，原子写，CSV 公式注入转义
    ├── requirements.txt
    ├── spec.md  acceptance.md  README.md  COMPLIANCE.md  DEPLOY.md
    ├── LICENSE
    ├── tests/
    │   ├── fake_server.py    # 桩服务：列表页/图片/403/429/500/空页/robots
    │   ├── test_parse.py     # 离线单测
    │   ├── test_acceptance.py# 端到端
    │   ├── verify_output.py  # 导出校验
    │   └── fixtures/
    └── out/                  # 运行产物（csv/json/jsonl/images）

---

## 9. 不做

1. 不登录、不绕验证码、不换 IP/UA、不做并发。
2. 不抓非公开内容、不抓评论用户、不做人物画像。
3. 不做跨运行增量、不写数据库。
4. 不做图片二次处理（不压缩、不裁剪、不 OCR）。
5. 不做 Web 界面/定时任务/上传。
6. 不下载详情页大图（只用列表页缩略图），不追外链。
