---
name: research-library-metadata-provenance-v4
description: 元数据溯源台账式科研资料库整理——字段字典先行，每个元数据字段都是一条带来源、证据、置信度的台账记录，多来源冲突按 admin_note > companion_table > content > filename > agent_inference 裁决，绝不猜测。
---

# 科研资料库元数据溯源台账（版本4）

## ① 触发与适用

当任务是把 `/input` 下杂乱的科研资料库（中文/特殊字符文件名、改名备份副本、管理性版本备注、伴随元数据表、压缩包、深层目录、重复文件、同一文档多个版本）整理为结构化库，并要求按 `/input/case.json` 的 `output_contract` 产出 `result.json` 时使用本技能。本技能的核心资产是**溯源台账**：任何元数据取值都必须能回答"从哪来、证据是什么、有多可信、与谁冲突过"。

## ② 执行协议（严格按序）

**step0 — 检查输入，先写 partial：**
```bash
ls /input        # 确认 case.json / task.md / 资料库文件
mkdir -p /app/work /app/output
python3 /skills/weekly-skill/scripts/finalize.py --input /input --work /app/work --output /app/output --config /skills/weekly-skill/config/field_dictionary.json --partial
```
partial result.json 保证即使后续超时/中断，`/app/output/result.json` 也已存在且诚实标注 `status=partial`。

**step1 — 必需字段进字典：** 若 `case.json` 或 `task.md` 指定了必需字段清单，把它写进字段字典的 `required`。管线会自动合并 `/input/case.json` 的 `required_fields`（数组或逗号分隔字符串）到 `/app/work/field_dictionary.json`；若题目用其他方式指定（如 task.md 正文），手工编辑 `/app/work/field_dictionary.json`，把对应字段的 `required` 置 `true`，缺失字段按字典 schema 新增。

**step2 — 跑管线（确定性工作全进脚本，不占模型预算）：**
```bash
python3 /skills/weekly-skill/scripts/provenance_pipeline.py --input /input --work /app/work --output /app/output
```
管线依次：扫描（流式 sha256、无权限登记、空目录登记、zip/tar stdlib 展开登记）→ 文件名解析 → 内容嗅探（前 64KB；PDF 仅在环境有 pdftotext 时调用）→ 伴随表 join → 管理备注解析 → 裁决 → 组织 library + manifest + 覆盖率报告 → finalize。

**step3 — Agent 只补 agent_inference 级字段（可选、克制）：** 管线跑完后，仅当 output_contract 必填字段仍有缺口且脚本证据不足时，Agent 才介入。把推断写成 JSONL 追加到 `/app/work/agent_candidates.jsonl`，每行格式：
```json
{"file": "<relpath>", "field": "<字段名>", "value": "<值>", "evidence": "<你看到的依据原文>", "confidence": 0.5}
```
`source` 会被强制标为 `agent_inference`（最低优先级，任何证据来源都可覆盖它）。然后重跑：
```bash
python3 /skills/weekly-skill/scripts/adjudicate.py  --input /input --work /app/work --output /app/output --config /skills/weekly-skill/config/field_dictionary.json
python3 /skills/weekly-skill/scripts/build_manifest.py --input /input --work /app/work --output /app/output --config /skills/weekly-skill/config/field_dictionary.json
```

**step4 — finalize：**
```bash
python3 /skills/weekly-skill/scripts/finalize.py --input /input --work /app/work --output /app/output --config /skills/weekly-skill/config/field_dictionary.json --final
```
核对 `/app/output/result.json`：`case_id` 正确、output_contract 全部字段在案（无产物可填的字段为 `null` 且 `uncertainty` 有说明）、`status/sources/uncertainty/change_records` 齐全。

## ③ 输出清单（/app/output）

| 文件 | 内容 |
| --- | --- |
| `result.json` | case_id + output_contract 全部字段 + status/sources/uncertainty/change_records |
| `library/` | 按已裁决元数据（project/year）组织的目录树，原名复制，重名加 `__N` |
| `manifest.json` | 每文件：字段值 + 每字段出处/置信度/证据/冲突 + 重复与版本关系 |
| `manifest.csv` | 人类可读清单，每字段带 `__source` 出处列（UTF-8-BOM，Excel 友好） |
| `duplicates.json` | 内容哈希判定的重复组（含保留主副本） |
| `versions.json` | 版本链：superseded_by + 差异摘要 + 依据 |
| `provenance.jsonl` | 逐字段台账：field/value/source/evidence/confidence/conflicts/rule |
| `field_coverage_report.md` | 字段填充率统计（必填字段缺失单列） |

## ④ 异常处理对照表

| 异常 | 处理 |
| --- | --- |
| 同一字段多来源冲突 | 按优先级 admin_note > companion_table > content > filename > agent_inference 裁决；落选证据全部保留在 `conflicts`，不丢弃 |
| 表格编码乱 | chardet 不可用，按 utf-8-sig → utf-8 → gb18030 → utf-16 依次尝试；全部失败用 utf-8+replace 并在证据中注明所用编码与告警 |
| PDF 无文本层 / 无 pdftotext | 登记 `content_unreadable.jsonl`（source=content, status=unreadable + 原因），绝不编造内容字段 |
| 无权限/不可读文件 | 登记 `readable=false` + 原因，计入"跳过"，进 uncertainty，不静默、不崩溃 |
| 坏 zip/tar | stdlib 展开失败登记到 scan_summary.archives，单条目坏不拖垮整包 |
| 空目录 | 登记 scan_summary.empty_dirs + uncertainty |
| 伴随表行匹配不到文件 | 登记 companion_unmatched.jsonl + uncertainty |
| 抽不到某字段 | 该字段为 `null`，覆盖率报告统计缺失；**绝不猜** |
| 单文件/单阶段失败 | try/except 隔离，记录后继续；阶段非零退出 → result.status=partial |

## ⑤ 不适用边界

- 不做全文语义理解、不做文献内容综述（那是检索/问答类任务）；
- 不修改 `/input` 原始文件（只读 + 复制到 library）；
- 不为凑必填字段编造取值——`agent_inference` 也必须有可见依据并标注最低置信度；
- 非文本二进制（docx/xlsx/图片，无专用解析器时）不猜内容，仅采信文件名/伴随表/管理备注来源。
