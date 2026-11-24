# 验收清单（Given / When / Then）

配套 `spec.md` v1.0。基准数字：每页 20 本、共 50 页；默认跑 2 页 = 40 本 + 40 张图。

## A. 采集量与翻页

**AC-01 默认 2 页（A）** Given 默认参数 When 运行 Then `pages=2 rows_kept=40`，CSV 40 行数据，JSON 长度 40
**AC-02 页数上限（A）** Given `--max-pages 1` When 运行 Then `pages=1 rows_kept=20`，`page` 全为 1
**AC-03 跟随 next（A）** Given 桩服务 3 页 When 运行 Then 请求序列为 `/page-1 → /page-2 → /page-3`，第 3 页无 next 即停
**AC-04 末页不越界（A）** Given 最后一页无 next When 处理 Then 正常结束，不再请求下一页 URL
**AC-05 空页正常收尾（A）** Given 越界页 200 但 0 条且无 next When 运行 Then 退出码 0 且 `errors` 有 `empty_page` warning

## B. 字段

**AC-06 必填非空（A）** Given 40 行输出 When 校验 Then `book_id/title/product_url/image_url` 全非空，`book_id` 唯一
**AC-07 标题取 title 属性（A）** Given 首行 When 检查 Then `title` 是完整书名（不是 "A Light in the ..." 截断文本）
**AC-08 价格解析（A）** Given `£51.77` When 解析 Then `price_gbp == 51.77`（数值，非字符串）
**AC-09 评分映射（A）** Given `class="star-rating Three"` When 解析 Then `rating == 3`；One..Five 全覆盖
**AC-10 库存归一（A）** Given "In stock" When 解析 Then `in_stock == True`
**AC-11 详情页可选（A）** Given `--with-detail` When 运行 Then `description` 与 `category` 非空；不加该参数时二者为空串且不请求详情页

## C. 图片

**AC-12 图片落盘（A）** Given `--max-pages 1` When 运行 Then `out/images/` 恰有 20 个文件，扩展名为 jpg/png/webp，大小 > 0
**AC-13 记录与图片关联（A）** Given 导出结果 When 检查 Then 每行 `image_file` 指向的文件存在
**AC-14 图片失败不丢记录（A）** Given 桩服务对某张图返回 404/非图片 When 运行 Then 该行仍在，`image_file` 为空，`errors` 记 `image_skipped`
**AC-15 幂等（A）** Given 已下载过 When 再跑一次 Then 不重复下载（同名跳过），文件数不变
**AC-16 `--no-images`（A）** Given 该参数 When 运行 Then 不创建 images 目录，`image_file` 全为空

## D. 去重

**AC-17 同书不重复（A）** Given 桩服务两页返回相同 20 本 When 运行 Then `rows_seen=40 rows_kept=20 dup=20`

## E. 异常

**AC-18 403 立即停（A）** Given 第 2 页 403 When 运行 Then 退出码 2，只请求 1 次，不请求第 3 页，第 1 页 20 行已导出
**AC-19 429 立即停（A）** Given 429 + `Retry-After: 30` When 运行 Then 记录 `retry_after=30`，退出码 2
**AC-20 5xx 重试 2 次（A）** Given 第 2 页恒 500 When 运行 Then 该页共 3 次请求后停止
**AC-21 单条字段坏只跳该条（A）** Given 某条缺 title When 运行 Then 跳过该条并记 `parse_missing_field`，其余照常
**AC-22 robots 禁止（A）** Given `Disallow: /` When 运行 Then 零页面请求，退出码 1

## F. 导出

**AC-23 CSV 可打开（A+M）** Given 导出文件 When 打开 Then 表头为 spec 中 11 列，utf-8-sig，含逗号书名不拆列
**AC-24 JSON 合法（A）** Given json 文件 When `json.load` Then 长度 40，每元素 11 个键
**AC-25 公式注入转义（A）** Given 书名以 `=` 开头 When 导出 CSV Then 该单元格以 `'` 前缀开头；JSON 中不变
**AC-26 原子写（A）** Given 运行结束 When 检查目录 Then 无 `.tmp` 残留

## 通过标准

A–F 全部通过；图片类（AC-12~16）允许在桩服务上验证，避免大量真实请求。
