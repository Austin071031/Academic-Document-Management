# 边界情况清单（对照实测行为）

| 情况 | 管线行为 | 证据位置 |
| --- | --- | --- |
| 中文/特殊字符文件名（空格、括号、【】、emoji） | UTF-8 全程；匹配用 NFC 归一化主干；library 路径组件清洗 `/ \` | files.jsonl / manifest.json |
| 改名备份副本（内容相同） | sha256 相同 → duplicates.json 同组，路径最短者为 keep | duplicates.json |
| 同一文档多版本（内容不同） | 管理备注 superseded_by 事实优先；否则剥离 vN/副本/最终版 标记后同主干按 mtime 成链；文本给 +/-/~ 行差异摘要 | versions.json |
| CSV 管理备注（"原文件,新文件"列 / "A 已被 B 替代"文本行） | 两种形态都解析为 facts.jsonl 事实，去重后生效 | facts.jsonl / versions.json |
| 伴随元数据表（UTF-8/GBK，含幽灵行） | 表头经 field_aliases 映射；按归一化主干 join；幽灵行进 companion_unmatched.jsonl + uncertainty | candidates.jsonl / uncertainty |
| 坏 zip / 坏 tar | expand 失败登记 scan_summary.archives(status=unreadable) + uncertainty；不崩溃 | scan_summary.json |
| zip 路径穿越条目（../、绝对路径） | 跳过该条目，不落地 | scan_summary.json |
| 巨型压缩包 | 单包 ≤2000 条目、单条目 ≤200MB 上限 | provenance_pipeline.py 常量 |
| 无权限文件 | stat/read 失败 → readable=false + 原因；进 uncertainty；计"跳过"不静默 | files.jsonl / result.json |
| 空目录 | 登记 scan_summary.empty_dirs + uncertainty | scan_summary.json |
| 深层目录 | os.walk 全深度；relpath 保留层级 | files.jsonl |
| PDF 有文本层且环境有 pdftotext | subprocess 取前 3 页套用内容嗅探器，证据注明 via pdf | provenance.jsonl |
| PDF 无文本层 / 无 pdftotext | 登记 content_unreadable.jsonl（source=content, status=unreadable + 原因） | content_unreadable.jsonl / uncertainty |
| docx/xlsx/图片等无二进制解析器 | 不猜内容；仅采信 filename/companion/admin 来源 | content_skipped.jsonl |
| 表格/文本编码混乱 | utf-8-sig → utf-8 → gb18030 → utf-16 依次尝试，记录实际编码；全失败 utf-8+replace + 告警 | evidence 字符串 |
| 文件名命中多个模式 / 字段冲突 | 全部产出候选，裁决器按优先级取值，落选进 conflicts | provenance.jsonl |
| 管理备注"字段: 值"库级默认 | file=`*` 候选，仅补缺，置信度 ×0.9 | provenance.jsonl |
| case.json 指定必需字段 | step1 合并进 work/field_dictionary.json 的 required，覆盖率报告单列缺失 | field_coverage_report.md |
| 超时/中断风险 | step0 先写 partial result.json | /app/output/result.json |
