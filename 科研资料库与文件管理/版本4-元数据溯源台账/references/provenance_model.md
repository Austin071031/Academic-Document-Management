# 出处模型与置信度定义

## 1. 两级台账

**候选（candidate）**——抽取器的原始产出，写入 `work/candidates.jsonl`：

```json
{"file": "<relpath>", "field": "year", "value": "2023",
 "source": "filename", "evidence": "pattern '项目_作者_年份_类型' group '3' on basename '项目A_张三_2023_实验记录.txt'",
 "confidence": 0.6, "ts": "…"}
```

**裁决记录（adjudicated record）**——每个 `(file, field)` 的最终台账行，
写入 `provenance.jsonl`（schema 见 `schemas/provenance.schema.json`）：

```json
{"file": "<relpath>", "field": "year", "value": "2023",
 "source": "companion_table", "evidence": "companion '元数据/伴随元数据.csv' row 2 col '年份' …",
 "confidence": 0.85,
 "conflicts": [{"value": "2024", "source": "filename", "evidence": "…", "confidence": 0.6}],
 "rule": "priority: admin_note > companion_table > content > filename > agent_inference",
 "adjudicated_at": "…"}
```

事实（fact）——管理备注解析出的关系型事实，写入 `work/facts.jsonl`：
`{"type": "superseded_by"|"alias", "old": "…", "new": "…", "source": "admin_note", "evidence": "…"}`

## 2. 六要素覆盖

| 要素 | 字段 |
| --- | --- |
| 对象 what | `file` + `field` |
| 结果 result | `value` |
| 来源 where | `source` |
| 依据 why | `evidence`（可定位到具体文件/行/列/正则） |
| 可信度 how sure | `confidence` |
| 时间 when | `ts` / `adjudicated_at` |

另附 `conflicts`（落选证据全保留）与 `rule`（裁决规则串内嵌每行，产物自证）。

## 3. 来源优先级与基准置信度

```
admin_note (0.95) > companion_table (0.85) > content (0.75) > filename (0.60) > agent_inference (0.50)
```

- **admin_note**：管理人显式维护的备注/版本说明，视为库的"地面真值"。
  库级默认（file=`*`）补用时 ×0.9。
- **companion_table**：结构化伴随表，行列可定位。
- **content**：正文嗅探。结构化正则命中 0.75；启发式标题行 0.65（在 candidate 级下调）。
- **filename**：命名约定解析，约定可能被违反，故低于正文。
- **agent_inference**：Agent 推断。制度性最低：必须写 `evidence`（所见原文），
  任何脚本证据来源都覆盖它；它存在的意义是"诚实标注这是推断"。

## 4. 冲突语义

- `conflicts` 只收**取值不同**的落选候选；同值多来源合并进
  `evidence` 的 `corroborated by:` 后缀（互证提升可信度但不改数值口径）。
- 冲突不是错误，是资料库的真实状态；裁决器记录冲突数量到
  `adjudicate_summary.json.fields_with_conflicts`，并汇总进 result.json 的 uncertainty。

## 5. 不可知与不可读

- 字段抽不到：manifest 中该字段 `null`，覆盖率报告统计，**不产生任何记录式猜测**。
- 文件不可读：`files.jsonl` 记 `readable=false` + 原因；
  内容不可读（PDF 无文本层等）：`content_unreadable.jsonl` 记
  `source=content, status=unreadable, reason=…`。二者都进 result.json 的 uncertainty。
