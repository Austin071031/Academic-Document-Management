# SUBMISSION — v2.0.0-案例组件补全

| 字段 | 内容 |
|---|---|
| 题目 | 科研资料库与文件管理（challenge-2bfd9194，玻尔产品周赛第四期） |
| 方向 | 案例组件补全：在版本1 确定性哈希账本流水线之上补齐「检索问答」与「恢复/重建索引」两个案例组件 |
| Attempt ID | attempt 108115 已提交，出分后回填 |
| 提交时间 | attempt 108115 已提交，出分后回填 |
| 评测状态 | attempt 108115 已提交，出分后回填 |
| 得分 | 已提交（attempt 108115，2026-11-25T09:10Z，官方 CLI 0.1.58；出分后回填） |
| Outcome | attempt 108115 已提交，出分后回填 |
| 评测摘要 | attempt 108115 已提交，出分后回填 |
| Bundle SHA-256 | attempt 108115 已提交，出分后回填 |

## 提交内容（本目录）

- `SKILL.md` — Skill 主文档（执行协议插入 step1b：pipeline → recover/qa → verify → finalize）
- `scripts/` — library_pipeline（基座全链路 + 末尾自动衔接）/ write_partial_result / finalize_result / validate_result（基座）＋ recover（恢复与重建索引）/ qa（检索问答）/ preflight_check（提交自检，v2 新增）
- `references/` — output_contract / edge_cases / method（基座）＋ reproduce.md（复跑命令清单，v2 新增）
- `schemas/`、`examples/minimal_example.md`、`README.md`、`CHANGELOG.md`、`GITHUB_URL.txt`

## 本地验证基线（合成 fixture，非平台数据）

- 全链路退出码 0；verify PASS 全 match；自动衔接 recover + qa；
- searches 命中带 文件:行号+片段 证据；recovery 按别名从同哈希组恢复并 sha256 校验一致；
- result.json 含 case_id + output_contract 全字段；preflight_check PASS。
- 详细命令与实测摘要见 README.md「自查方法」。

## 迭代记录

- v2.0.0（2026-11-25）待首次提交。相对版本1 的丢分诊断：基座只有盘点/组织/去重/版本链/校验，
  案例画像中的 "searches/questions" 与 "actual recovery/index operations" 两个组件整项缺失；
  本版定向补齐，基座其余行为不变。得分与评测摘要attempt 108115 已提交，出分后回填。
