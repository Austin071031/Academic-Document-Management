# SUBMISSION — 版本3-谓词约束过滤

| 字段 | 内容 |
|---|---|
| 题目 | 科研文件智能检索（challenge-139745c7，玻尔产品周赛第四期） |
| 方向 | 谓词约束过滤：任务条件编译为强类型谓词、逐谓词执行与审计、不可满足如实报告绝不放宽 |
| Attempt ID | [89367](https://play.bohrium.com/attempt/89367) |
| 提交时间 | 2026-11-19 07:37 UTC |
| 评测状态 | **scored（final）** |
| 得分 | **67.6667 / 100** |
| Outcome | partial |
| 评测摘要 | "Received and graded in full. Solid — refine for a more complete and rigorous solution." |
| Bundle SHA-256 | `ccb15fc7fd82254cc67964f9f9354b607d941286d400f1d75e262dcaeb7a8645` |

## 提交内容（本目录）

- `SKILL.md` — Skill 主文档
- `scripts/` — inventory / extract / segment / constraints（旗舰）/ retrieve / verify / report
- `README.md`、`examples/EXAMPLE.md`（合成演示，非正式案例结果）、`GITHUB_URL.txt`

## 本地验证基线（合成案例，非平台数据）

- 5 条谓词（year/project_id/doc_type/batch/permission）编译执行正确，
  `filter_audit.json` 逐文档给出 kept/excluded 理由；verify 5/5 通过。

## 迭代记录

- v1.0.0（2026-11-19）首次提交，得分 67.6667。后续改进方向：扩谓词语法
  （数值比较、日期表达"早于/晚于"、复合否定条件），并将谓词执行结果直接
  注入 answer 模板，保证回答逐谓词回应、与审计完全一致。
