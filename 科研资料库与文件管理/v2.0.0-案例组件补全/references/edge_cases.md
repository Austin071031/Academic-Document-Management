# 边缘情况处置

| 情况 | 处置 | 证据位置 |
|---|---|---|
| 超大文件 | 1 MiB 分块流式哈希，不整读入内存；复制用 copyfileobj/copy2 | inventory.jsonl size/sha256 |
| 空文件（0 字节） | 正常入库；不参与去重（避免误并不相关空文件），列入 duplicates.json.excluded_empty_files_from_dedup | duplicates.json |
| 空目录 | scan 记录到 scan_summary.json.empty_dirs，不产生账本文件行 | scan_summary.json |
| 深目录 | os.walk 递归，无深度限制；depth 字段记录层级 | inventory.jsonl depth |
| 中文/特殊字符文件名 | 全程 UTF-8；unicodedata NFC 归一化；落盘名经 sanitize（替换 \\/:*?"<>| 与控制字符）；打印 errors=replace | library/ 实际树 |
| 只读/无权限文件 | inventory 记 readable=false + error 原因；apply 记 skip_unreadable；写入 result.uncertainty；绝不静默跳过 | inventory.jsonl / operation_log.jsonl |
| 损坏 zip/tar | is_zipfile/is_tarfile 预检失败 → 按普通文件入库并记 archive_error；展开中成员级失败只记该成员 | inventory.jsonl archive_error / scan_summary.extraction_errors |
| 压缩包路径穿越 | 拒绝绝对路径与 `..` 组件的成员名，跳过该成员 | scan_summary.extraction_errors |
| 同名文件（不同内容） | plan 阶段确定性分配 `__dupN` 后缀，绝不覆盖 | plan.json / library 树 |
| 内容相同名字不同 | sha256 分组，mtime 最旧为 canonical，其余 duplicate_of（不重复复制） | duplicates.json |
| 同一文档多版本 | 归一化 stem difflib ≥0.75 聚类 + mtime 升序，superseded_by 指向更新者；哈希相同者算重复而非版本 | versions.json |
| case.json/task.md | 登记为 kind=metadata，不入库不参与去重 | inventory.jsonl |
| 伴随表编码 | utf-8-sig / utf-8 / gb18030 依次尝试，最终 errors=replace | （读取容错，无单独日志） |
| 打印非 UTF-8 环境 | stdout reconfigure errors=replace | — |
