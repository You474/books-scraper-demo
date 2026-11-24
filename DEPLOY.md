# 部署与预览说明

命令行采集器，无 Web/小程序/常驻服务。「部署」= 找台机器跑起来；「预览」= 看 CSV/JSON 和 images/。

## 1. 本地

    git clone <repo-url> books-scraper-demo
    cd books-scraper-demo
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1        # macOS/Linux: source .venv/bin/activate
    pip install -r requirements.txt
    python scraper.py

## 2. 服务器定时（可选）

    # 每天 04:00 抓 2 页
    0 4 * * * cd /opt/books-scraper-demo && ./.venv/bin/python scraper.py --delay 2.0 --out-dir /var/data/books >> /var/log/books.log 2>&1

注意：每次全量重跑、out/ 会累积（图片幂等但 csv/json 每次新文件），请自行清理；不要调低 delay。

## 3. 预览

| 产物 | 怎么看 |
| --- | --- |
| \`books_*.csv\` | Excel/WPS 双击（utf-8-sig，中文不乱码） |
| \`books_*.json\` | 编辑器，或 \`python -c "import json;print(len(json.load(open('out/books_x.json',encoding='utf-8'))))"\` |
| \`out/images/\` | 文件管理器缩略图；文件名 = \`book_id\`，可与 CSV 对应 |
| 完整性 | \`python tests/verify_output.py out\books_x.csv out\books_x.json out\images\`（12 项断言） |
| 错误 | \`type out\errors_x.jsonl\`（macOS: cat） |

## 4. 无外网演示

    python tests/fake_server.py 8010 --scenario ok
    python scraper.py --base-url http://127.0.0.1:8010/ --delay 0.2 --max-pages 1

## 5. 不在范围

容器化、CI/CD、Web 界面、多机分布式、代理池——都与本项目目标无关，且与「低负载采集」冲突。

## 6. 清理

    rm -rf out/ .venv __pycache__ tests/__pycache__
