# 版本3 · 谓词约束过滤 — 使用与方法说明

## 这个版本解决什么问题

带硬条件的检索（年份/项目编号/文件类型/批次/版本/权限/目录范围）最常见的失败是
**静默放宽条件**或**条件解析错误导致误报无结果**。本版本把任务文本编译为
**强类型谓词**，逐谓词执行、计数、审计，条件不满足时如实报告并给出冲突诊断。

## 谓词类型与来源模式

| 字段 | 识别模式（任务文本） | 执行方式 |
|---|---|---|
| year | `YYYY–YYYY`、`YYYY年`、`近N年` | 正文前部年份元数据区间匹配 |
| project_id | `项目/课题/基金编号 XT-2021-0453`、`[A-Z]{2,6}[-_]?\d{4,10}` | 全文大写化包含匹配 |
| doc_type | `PDF/Word/Excel/PPT/扫描件` | 类别硬匹配 |
| version | `最新版/终版/vN/旧版` | lineage 角色/标签匹配 |
| batch | `批次 B7`、`batch B7` | 全文包含匹配 |
| path_scope | 引号或书名号内的目录名 | 路径包含匹配 |
| permission | 默认硬约束 | 仅可读文件 |

每条谓词记录 `source_quote`（任务原文片段）与 `confidence`；输出
`predicates.json`（逐谓词 docs_matched/status）、`filter_audit.json`
（逐文档 kept/excluded + 理由）、`filter.json`（机器可执行条件）。

## 硬过滤纪律

1. 条件不满足的文档一律排除，理由入审计；
2. 全部谓词不可满足 → 结果集为空 + 冲突诊断，**绝不放宽**；
3. 放宽只能来自任务原文的明确指示；
4. answer 中不得出现审计之外文件的证据。

## 依赖与安装

- Python ≥3.9（仅标准库）；`constraints.py` 内部复用 retrieve 的年份元数据构建器。
- 无网络依赖。安装＝复制到 `/skills/weekly-skill`。

## 目录约定

```
scripts/constraints.py  【旗舰】约束编译+执行（步骤3.5）
scripts/{inventory,extract,segment,retrieve,verify,report}.py  核心流水线
```

## 运行示例

见 `SKILL.md` 第 4、8 节；合成演示见 `examples/EXAMPLE.md`（标注为示例）。

## 限制与失败处理

- 语义近似条件（"较新的版本"）按显式标签/日期判定，语义解释由模型在 answer 中
  另行说明并标注不确定性；
- 年份以正文前部出现者为准，附录参考文献年份不参与文档年份判定；
- 条件冲突（类型互斥等）在审计中可见，结果为空并诊断。

## 维护

识别模式集中在 `compile_predicates()`；新增谓词类型需同步 `execute()` 与本文档。
