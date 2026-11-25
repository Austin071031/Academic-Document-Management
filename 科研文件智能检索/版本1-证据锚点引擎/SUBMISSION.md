# SUBMISSION — 版本1-证据锚点引擎

| 字段 | 内容 |
|---|---|
| 题目 | 科研文件智能检索（challenge-139745c7，玻尔产品周赛第四期） |
| 方向 | 证据锚点引擎：印刷页↔物理页偏移校正、双栏重排、跨页题注续接、逐字回链校验 |
| Attempt ID | [89362](https://play.bohrium.com/attempt/89362) |
| 提交时间 | 2026-11-19 07:29 UTC |
| 评测状态 | **scored（final）** |
| 得分 | **68.0 / 100** |
| Outcome | partial |
| 评测摘要 | "Received and graded in full. Solid — refine for a more complete and rigorous solution." |
| Bundle SHA-256 | `936779c57c88808255d802424c27d8e58b1ae28f81cc14beb2c415a9f16ff344` |

## 提交内容（本目录）

- `SKILL.md` — Skill 主文档（YAML frontmatter + 运行契约 + 标准工作流）
- `scripts/` — inventory / extract / pagefix（旗舰）/ segment / retrieve / verify / report
- `README.md`、`examples/EXAMPLE.md`（合成演示，非正式案例结果）、`GITHUB_URL.txt`

## 本地验证基线（合成案例，非平台数据）

- 端到端流水线跑通；verify 逐字校验 5/5 通过；物理页 2 经 pagefix 校正为印刷页 12/22；
- report finalize 0 问题；边界测试（缺失输入根目录）优雅降级并记录 `path_missing`。

## 迭代记录

- v1.0.0（2026-11-19）首次提交，得分 68.0。后续改进方向：评审摘要提示需
  "更完整与更严谨"——计划补充多查询批处理与证据聚类去重，并强化对任务多问题
  的逐项覆盖后再迭代。
