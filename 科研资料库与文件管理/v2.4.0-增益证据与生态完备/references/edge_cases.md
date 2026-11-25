# 边界情况处理清单

| # | 情况 | 行为 | 证据位置 |
|---|---|---|---|
| 1 | 中文/特殊字符文件名（`<>:"/\|?*`、全角字符） | NFKC 归一化；非法字符→`_`；空白折叠为单空格；分量截断 80 字符、总路径 240 字符；Windows 保留名（CON 等）加前缀 | 目标路径 + plan notes |
| 2 | 规范化后目标冲突 | 追加 `__dupN`（N≥2 递增），绝不覆盖既有文件 | 目标路径含 `__dupN` |
| 3 | 改名备份副本（内容相同） | 流式 sha256 分组进 duplicates.json，视为别名，全部保留 | duplicates.json |
| 4 | 同一文档多历史版本 | 基础名（剥离 v1/v2/副本/final/修订/旧版 等 token）+ 扩展名分组；哈希不同才算版本链；按 mtime 排序写 superseded_by 与 size 差异 | versions.json |
| 5 | 坏 zip / 非标准压缩包 | zipfile/tarfile 异常捕获，登记 error；文件本体仍按路由规则归位 | plan.archives + uncertainty |
| 6 | 合法 zip/tar | 展开登记成员清单（不递归展开内容文件） | plan.archives |
| 7 | 空目录 | 移入 `/app/output/quarantine/<原相对路径>`，journal 记 reverse | journal + quarantine |
| 8 | 无权限文件 | open/stat 失败 → skipped，`readable=false` + 系统错误原因 | plan.skipped |
| 9 | 无权限目录 | os.walk onerror 捕获（默认会静默跳过，必须显式登记） | plan.skipped |
| 10 | 元数据三路来源冲突 | 伴随 CSV > 管理备注 md > 文件名模式，逐字段留出处 `{value, source, evidence}` | metadata_provenance |
| 11 | 元数据缺失 | 字段用 fallback（如 `unknown-project`、`undated`），notes/uncertainty 记原因，绝不猜 | plan notes |
| 12 | 字段值越界（不在字段字典） | 用字段字典 fallback 值；notes 记录原始值 | plan notes |
| 13 | case.json / task.md | 识别为任务输入，跳过归位，登记原因 | plan.skipped |
| 14 | 超大文件 | 流式 sha256（1 MiB 分块），不整读入内存 | — |
| 15 | 题目自定义目录约定 | step1 翻译进配置；同义字段（topic/subject/kind/category/date）从规范字段镜像 | layout_template.effective.json |
| 16 | 中途崩溃 | organize 兜底 handler 重写 partial result.json；finalize 原子写 | result.json |
