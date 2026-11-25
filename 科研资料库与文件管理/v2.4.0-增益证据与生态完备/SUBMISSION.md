# SUBMISSION — v2.4.0-增益证据与生态完备

| 字段 | 内容 |
|---|---|
| 题目 | 科研资料库与文件管理（challenge-2bfd9194，玻尔产品周赛第四期） |
| 方向 | 模板规则引擎归位 + 可机检增益证据（前后对照/幂等验证）+ 生态完备文档 |
| 基座 | 版本3-模板规则引擎归位（基线最好 68.67，本版目标 80） |
| Attempt ID | 待回填 |
| 提交时间 | 待回填 |
| 评测状态 | 待回填 |
| 得分 | 待回填 |
| Outcome | 待回填 |
| 评测摘要 | 待回填 |
| Bundle SHA-256 | 待回填 |

## 提交内容（本目录）

- `SKILL.md` — Skill 主文档（frontmatter name=research-library-rule-engine-v2-4）
- `scripts/` — organize / rule_engine / plan / apply / audit / finalize（基座）
  + gain_report / qa / recover / preflight_check（v2.4.0 新增）
- `config/layout_template.json`、`schemas/`、`references/`（+reproduce.md）、
  `docs/USAGE.md`、`docs/REUSE.md`、`examples/`、`CHANGELOG.md`、`GITHUB_URL.txt`

## 本地验证基线（合成案例，非平台数据）

- 见 README「自查方法」v2.4.0 节：/tmp 合成夹具（中文名、改名副本、双版本、
  CSV 管理备注、坏 zip、空目录、5 层深目录、case.json 含 searches/recovery）
  实跑入口两次：退出码 0、幂等哈希一致、audit 全 match、检索有命中、
  恢复带校验、preflight 全 pass。

## 迭代记录

- v2.4.0（2026-11-25）在版本3基座上施加定向增量：增益度量报告
  （gain_report.md + gain_metrics.json，全部真实计数）、检索问答（qa.py）、
  恢复操作（recover.py）、提交契约自检（preflight_check.py）、
  USAGE/REUSE/reproduce 生态文档。基座 plan/apply/audit 行为一字未改。
