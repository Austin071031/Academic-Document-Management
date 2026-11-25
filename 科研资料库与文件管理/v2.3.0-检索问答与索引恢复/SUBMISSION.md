# SUBMISSION — v2.3.0 检索问答与索引恢复

- 挑战：玻尔 playground 周赛第四期「科研资料库与文件管理」
  （challenge-2bfd9194）
- 基座：版本5-长期归档交付包（archive-first）
- 版本：v2.3.0（skill name: research-library-archive-handoff-v2-3）
- 提交日期：2026-11-25

## 本版定位

案例画像显式包含 "searches/questions and actual recovery/index
operations"。本版定向增量只做两件事并做到最强：

1. **检索问答证据化**（answer_questions.py）：字符串/对象形态的
   searches/questions 全兼容；每条给出
   {answer, hits:[{path,line,snippet}], evidence_complete,
   no_evidence_reason}；无命中绝不编答案；query_log.jsonl 记录
   查询语句/耗时/命中数供效率核验。
2. **真实恢复/索引操作**（recovery_ops.py）：按 文件名/别名/sha256
   前缀从归档包、账本、压缩包登记、input 原始树逐级恢复，逐字节
   校验；恢复后联动重建 FTS5 中文索引；全量写 recovery_log.jsonl。
   两步由 archive_pipeline.py 自动衔接（幂等、失败记账不崩溃），
   结果并入 result.json 的 sources/summary/change_records。

## 提交内容

- SKILL.md（frontmatter description 235B ≤600B/900B 双上限）
- scripts/：archive_pipeline / organize / build_index / query_index /
  make_archive / verify_archive / finalize / lib（基座原样）
  + recovery_ops / answer_questions / preflight_check（本版新增）
- references/：output_contract / edge_cases / archive_spec /
  reproduce.md（新增）
- schemas/ examples/ selftest/ _bundle/ CHANGELOG.md README.md
  GITHUB_URL.txt preflight_report.json

## 契约自检

`python3 scripts/preflight_check.py` → preflight_report.json：
pass=true（≤50 文件、单文件 ≤500KB、总 ≤2MB、全 UTF-8、无符号链接、
无二进制、frontmatter 合法）。

## 评分记录

| Attempt | 日期 | 得分 | 备注 |
|---|---|---|---|
| 1 | 2026-11-25 | 待回填 | v2.3.0 首次提交；基线最好 68.67，目标 80 |

得分待平台运行后回填。
