# SUBMISSION — v2.2.0-元数据正确性强化

| 字段 | 内容 |
|---|---|
| 题目 | 科研资料库与文件管理（challenge-2bfd9194，玻尔 playground 周赛第四期） |
| 方向 | 元数据正确性强化：检索问答带引用证据 + 恢复/索引重建 + 字段正确性闸门 + 提交自检 |
| Attempt ID | 待回填 |
| 提交时间 | 待回填 |
| 评测状态 | 待回填 |
| 得分 | 待回填（基线最好 68.67，目标 80） |
| Bundle SHA-256 | 待回填 |

## 提交内容（本目录）

- `SKILL.md` — Skill 主文档（name=research-library-metadata-provenance-v2-2）
- `config/field_dictionary.json` — 字段字典（裁决规则单一事实来源）
- `scripts/` — 基座 9 脚本 + 新增 `qa_cite.py`（检索问答+引用证据）、
  `recover.py`（恢复+索引重建）、`preflight_check.py`（提交契约自检）；
  定向修改 `build_manifest.py`/`finalize.py`/`provenance_pipeline.py`
  （正确性闸门、产物映射、qa/recover 自动衔接），基座其余行为一字未改
- `references/` — 输出契约/溯源模型/边界案例 + 新增 `reproduce.md`（复跑命令清单）
- `README.md`、`CHANGELOG.md`、`examples/`、`schemas/`、`GITHUB_URL.txt`

## 丢分诊断与对策（相对基线 68.67）

1. **缺检索问答组件** → `qa_cite.py`：library/ 倒排索引（中文 bigram 兜底），
   答案逐条带 {文件,行号,原文片段} 引用证据 + 该文件元数据出处；
   无证据诚实 no_evidence+缺什么。
2. **缺恢复/索引组件** → `recover.py`：按文件名/哈希从扫描账本与压缩包登记恢复、
   sha256 校验、recovery_log 留痕、manifest 与检索索引自动重建。
3. **正确性/完整性不可机检** → 字段正确性闸门：必填字段填充率、冲突未决数、
   低置信字段数写入 `result.json.summary` 与覆盖率报告。

## 本地验证基线（合成案例，非平台数据）

见 README.md §7「自查方法」：/tmp 合成夹具真实运行，管线退出码 0，
provenance/search_results/recovery_log/正确性闸门/preflight 全部核对点通过。

## 迭代记录

- v2.2.0（2026-11-25）基座=版本4-元数据溯源台账，施加上述定向增量，首次提交待评测。
