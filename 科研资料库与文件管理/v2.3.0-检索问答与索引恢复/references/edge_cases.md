# 边界情况登记与处理对照

| # | 情况 | 登记位置 | 处理 |
|---|---|---|---|
| 1 | 中文/特殊字符/空格/emoji 文件名 | 全链路 UTF-8，os.walk 原样处理 | 保留原命名归档；tar 成员名原样写入 |
| 2 | 改名备份副本（`.bak`/`副本`/`(1)`/`_old` 等） | duplicates.json | 内容 sha256 相同 → `duplicate_of` 指向规范副本；不同哈希但同主干 → 进 versions.json |
| 3 | 同一文档多版本 | versions.json | norm_stem 剥离版本后缀聚类，mtime 排序，`superseded_by` 指向更新版，附 difflib added/removed 摘要 |
| 4 | 管理性备注 CSV/md、伴随元数据表 | organize 正常归位（data/text 类） | manifest provenance 记录来源，不覆盖真实元数据 |
| 5 | 压缩包（zip/tar/tgz/tar.gz） | extracted.json + inventory.jsonl | stdlib 展开到 `_extracted/`；逐成员 realpath 防 zip-slip/tar-slip |
| 6 | 坏压缩包（截断/BadZipFile） | extracted.json status=failed + 原因 | 原包仍归位归档，不崩溃 |
| 7 | 非 stdlib 格式（7z/rar 等） | extracted.json status=not_extracted | 如实登记，不解即归档 |
| 8 | 深层目录 | library/<项目>/<年份>/<类型>/ 下保留原相对路径 | 无递归深度限制 |
| 9 | 无权限/不可读文件 | inventory.jsonl `readable=false`+reason | 计 skipped；以 sha256 实际打开失败为准（root 下 access() 可能误报） |
| 10 | 重复文件（内容级） | duplicates.json | 以内容哈希判定，不按文件名 |
| 11 | 空目录 | organize_report.json `empty_dirs` | 登记留痕 |
| 12 | 二进制/超大文本 | build_index 跳过全文索引（is_text=0 或 >8MiB） | files 表仍登记元数据 |
| 13 | sqlite 无 FTS5 | index meta `degraded=true` | 退化为 LIKE 检索，result uncertainty 注明 |
| 14 | 磁盘不足（归档创建失败） | archive_build_error.json | 先保留 manifest/账本与 partial result.json |
| 15 | 归档被篡改/损坏 | verify_report.json mismatch/missing | status 降级，不谎报 ok |
| 16 | 检索无命中 | search_results.json answered=true, hits=[] | 如实空命中，不编造 |
| 17 | case.json 缺 case_id | 全链路 fallback `unknown_case` | 归档名 `unknown_case_archive.tar.gz` |
| 18 | retention/access_level 无出处 | manifest/result | 填 `unspecified`，evidence 注明"未抽到" |

## 判定依据

- 去重与版本**只按内容 sha256 / 归一化主干**判定，绝不按文件名猜测；
- "跳过"一律带 reason 进账本（inventory.jsonl），不允许静默；
- 校验（verify_archive.py）与打包（make_archive.py）相互独立，
  verify 只信 SHA256SUMS 与解包结果。
