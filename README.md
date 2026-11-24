# books-scraper-demo

图文类公开数据采集 Demo：抓取 [books.toscrape.com](https://books.toscrape.com/) 的商品列表，解析文本字段并**下载封面图**，
图片与记录通过 \`book_id\` 关联，导出 CSV / JSON，附完整测试与验收证据。

> **合规先行**：只采公开页面、串行限速、不登录、不绕验证码。使用前请读 [COMPLIANCE.md](COMPLIANCE.md)。

---

## 1. 环境

| 项 | 要求 |
| --- | --- |
| Python | ≥ 3.9（开发验证 3.11.4） |
| 依赖 | \`requests==2.34.2\`、\`beautifulsoup4==4.15.0\`（html.parser，无需 lxml） |
| 磁盘 | 默认 2 页约 0.4 MB 图片；50 页全量约 20 MB |

## 2. 安装

    cd books-scraper-demo
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1          # macOS/Linux: source .venv/bin/activate
    python -m pip install -U pip
    pip install -r requirements.txt

## 3. 运行

    python scraper.py                     # 默认 2 页 / 40 本 + 40 张封面图
    python scraper.py --max-pages 5       # 5 页 / 100 本
    python scraper.py --no-images         # 只采文本
    python scraper.py --with-detail       # 额外抓详情页（简介 + 分类），请求数翻倍
    python scraper.py --out-dir D:\data\books --delay 2.0

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| \`--base-url\` | books.toscrape.com | 可指向本地桩服务 |
| \`--max-pages\` | 2 | 上限 50（站内共 50 页 / 1000 本） |
| \`--delay\` | 1.0 | 相邻请求间隔秒，下限 0.2，不接受 0 |
| \`--out-dir\` | out | 输出目录 |
| \`--format\` | both | both / csv / json |
| \`--no-images\` | 关 | 关闭封面图下载 |
| \`--with-detail\` | 关 | 抓详情页补 \`description\` / \`category\` |

### 退出码

| 码 | 含义 |
| --- | --- |
| 0 | 正常结束（无 next / 达页数上限 / 空页收尾） |
| 1 | 前置失败：参数非法、robots 禁止、写入失败 |
| 2 | 采集中止但已保存部分数据：403 / 429 / 4xx / 5xx 重试后失败 / 空页有 next / 分页成环 / 一条没采到 |

## 4. 输出

    out/
    ├── books_YYYYmmdd_HHMMSS.csv     # utf-8-sig，Excel 直开
    ├── books_YYYYmmdd_HHMMSS.json    # 顶层数组，ensure_ascii=False
    ├── errors_YYYYmmdd_HHMMSS.jsonl  # 一行一个事件（无异常则为空文件）
    └── images/
        └── <book_id>.jpg             # 封面图，文件名即 book_id

### 字段（11 列）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| \`book_id\` | str | 商品页 URL 的 sha256 前 12 位；图片名与去重键 |
| \`title\` | str | **取自 \`title\` 属性**（页面文字被截断成 "A Light in the ..."） |
| \`price_gbp\` | float | 由 \`£51.77\` 解析为 \`51.77\` |
| \`rating\` | int | 1–5，由 \`star-rating Three\` 等 class 映射 |
| \`in_stock\` | bool | 由 "In stock" 归一 |
| \`category\` | str | 仅 \`--with-detail\` 时有值 |
| \`product_url\` | str | 绝对地址 |
| \`image_url\` | str | 封面图绝对地址 |
| \`image_file\` | str | \`images/<book_id>.jpg\`；下载失败为空串 |
| \`description\` | str | 仅 \`--with-detail\` 时有值 |
| \`page\` | int | 列表页码，1 起始 |

## 5. 自测

    python -m unittest discover -s tests -v     # 27 个用例，约 110s（含桩服务端到端）
    python tests/verify_output.py out\books_x.csv out\books_x.json out\images

    # 手动复现异常（另开窗口）
    python tests/fake_server.py 8010 --scenario 429
    python scraper.py --base-url http://127.0.0.1:8010/ --delay 0.2 --max-pages 3

桩服务场景：\`ok / 403 / 429 / 500 / emptynext / emptyend / noquotes / disallow / absent / duplicate / badimage\`

## 6. 已知限制

1. **选择器与目标站绑定**：\`article.product_pod\`、\`h3 a[title]\`、\`p.price_color\`、\`p.star-rating\`、\`ul.pager li.next\`；换站必须改 \`parse_list_page\`。
2. **默认只跑 2 页**（40 本）：这是刻意的礼貌上限，看全量请显式 \`--max-pages 50\`。
3. **图片只下缩略图**：不追详情页大图，不做压缩/裁剪/OCR。
4. **\`category\` 与 \`description\` 需要 \`--with-detail\`**：否则为空串，且请求数翻倍（每本多 1 次）。
5. **不做跨运行增量**：每次全量；图片已存在则跳过（幂等），但 CSV/JSON 每次新文件。
6. **403/429 不重试**：只记录并停止。
7. **robots.txt 为 404**（实测）：记为 \`robots=absent\` 后继续，保持 1s 间隔；5xx 时按「无法确认」把间隔抬到 2s。
8. **CSV 公式转义只作用于 CSV**：以 \`= + - @\` 开头的文本加前导 \`'\`（CWE-1236），JSON 保持原样。
9. **图片版权**：封面图版权归出版社/作者，仅本地留存，不要二次分发。
10. **无并发**：单进程串行，2 页约 67s（含 40 张图）。

## 7. 故障排查

| 现象 | 处理 |
| --- | --- |
| pip 装不上 | 显式镜像 \`-i https://pypi.tuna.tsinghua.edu.cn/simple\`；或离线 wheel |
| 端口 8010 被占 | \`python tests/fake_server.py 8011\` 并把 \`--base-url\` 改成对应端口 |
| 图片全是 0 张 | 看 \`errors_*.jsonl\` 的 \`image_skipped\`；多半是站点图床不可达或 Content-Type 非 image/* |
| 退出码 2 且 \`stop=http_forbidden\` | 站点限流，停手，别换 UA/IP 硬顶 |
| Excel 打开乱码 | 本程序写 utf-8-sig；仍乱码用「数据 → 从文本/CSV 导入」指定 UTF-8 |

## 8. 文件结构

    books-scraper-demo/
    ├── scraper.py            # 翻页、字段解析、图片下载、去重、编排
    ├── export.py             # CSV/JSON/JSONL，原子写，公式注入转义
    ├── requirements.txt
    ├── spec.md               # 规格（字段/翻页/图片/异常）
    ├── acceptance.md         # 26 条 Given/When/Then
    ├── ACCEPTANCE_REPORT.md  # 验收证据
    ├── README.md  COMPLIANCE.md  DEPLOY.md  LICENSE
    ├── tests/
    │   ├── fake_server.py    # 桩服务（列表页/详情页/图片/异常）
    │   ├── test_parse.py     # 离线单测
    │   ├── test_acceptance.py# 端到端
    │   ├── verify_output.py  # 导出校验（12 项）
    │   └── fixtures/         # 真实页面快照
    └── out/                  # 运行产物

## 9. 许可

代码 MIT，见 [LICENSE](LICENSE)。**采集到的封面图与书籍简介版权归原权利人**，不在代码许可范围内；站点条款优先，见 [COMPLIANCE.md](COMPLIANCE.md)。
