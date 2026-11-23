# 表 3 · 版本骨架对照（阅读批注与知识沉淀）

来源：仓库实际目录（`find 阅读批注与知识沉淀/v1.0.0 -type f`，2026-11-23 实采）。
本题目前仅 1 个历史版本，故"共有文件"= v1.0.0 全部文件（22 个文本文件，另仓库内残留
`scripts/__pycache__/*.pyc` 为提交包外产物——CLI 打包时自动跳过 `__pycache__`，不影响评测；
v2.0.0 将在仓库侧清除该残留）。

## v1.0.0 文件清单（= 基线资产白名单取数依据）

| 文件 | 作用（实测读取） |
|-|-|
| `SKILL.md` | 双工作流编排指南；frontmatter name=annotation-knowledge-sink；description 1046B |
| `scripts/pipeline.py` | 工作流 A：盘点→PDF 批注提取→锚点校验→笔记结构化→关联/版本归并→SQLite 索引→result.json（含与工作流 B 的合并逻辑） |
| `scripts/search.py` | 工作流 A 检索入口：FTS5 + CJK 二元组回退 + 结构化过滤 + 召回报告 |
| `scripts/inspect_case.py` | 工作流 B：读取 case.json/task.md → brief.json（只读结构化，不推断） |
| `scripts/inventory.py` | 工作流 B：哈希/魔数嗅探/权限/PDF 页数与文本层检测 → inventory.json/csv |
| `scripts/extract_refs.py` | 工作流 B：元数据提取（标题/作者/年份/DOI/arXiv/关键词，逐字段 source+confidence） |
| `scripts/plan.py` | 工作流 B：类型判定、版本分组（并查集）、去重、命名、目录归属 → plan.json |
| `scripts/apply.py` | 工作流 B：复制式入库、幂等、冲突不覆盖、审计日志 + rollback.sh |
| `scripts/report.py` | 工作流 B：result.json 汇总（含 output_contract 键名启发自动映射） |
| `scripts/validate_output.py` | 工作流 B：机读自查（契约字段/哈希一致/审计完备 → selfcheck.json） |
| `scripts/run_pipeline.sh` | 工作流 B 一键链：inspect→inventory→extract→plan→apply→report→validate，失败保底 partial |
| `schemas/note.schema.json` | 笔记 JSON Schema |
| `rules/link_rules.md` | 关联判定规则说明 |
| `references/edge_cases.md` | 异常与边界处置表 |
| `references/naming_rules.md` | 命名模板降级链 |
| `references/output_schema.md` | 输出布局与 result.json 字段说明 |
| `references/taxonomy_and_tags.md` | 文档类型 T0–T11 与受控标签词表 |
| `references/worked_example.md` | 工作流 B 走查示例 |
| `docs/USAGE.md` | 使用与方法说明（双工作流总览 + A 详解） |
| `examples/minimal_example.md` | 最小调用示例（标注为示意） |
| `CHANGELOG.md` | 版本变更记录 |
| `GITHUB_URL.txt` | GitHub 链接（提交根路径必备） |

## 跨题资产盘点（§1.2-5，L4 候选，备后用）

- 科研知识库问答 v1.0.0：`scripts/kb_*.py` 五件套（inventory/extract/index/search/result/versions），
  description 690B 且出分 66.0 → frontmatter 写法可作合规参照。
- 文献与资料自动分类 v1.0.0：description 1011B 且出分 64.6667 → 1024B 上限的边界实证。
- 科研文件智能检索（5 方向系列）、科研资料库与文件管理（5 方向系列）：
  存在 direction.json 式方向元数据与单方向分化实践，v2.0.0 仅借鉴其 direction.json 建制，
  不做方向分化（契约层修复分支禁止方向迭代）。

## 结论

- 共有文件 22 个全部纳入白名单；v2.0.0 必须为其超集（R1）。
- 无 submission.md / direction.json / 根 README 索引 → v2.0.0 补齐（建制缺失项）。
