# SUBMISSION — 版本5-自校验审计工作流

| 字段 | 内容 |
|---|---|
| 题目 | 科研文件智能检索（challenge-139745c7，玻尔产品周赛第四期） |
| 方向 | 自校验审计工作流：交付前五道机器 gate + 运行日记 + 输出哈希清单 + 复跑指引 |
| Attempt ID | [89374](https://play.bohrium.com/attempt/89374) |
| 提交时间 | 2026-11-19 07:47 UTC |
| 评测状态 | **pending_review（evaluation_error，未出分）** |
| 得分 | —（平台评测器执行失败，非答案判定） |
| Bundle SHA-256 | `d8c02aae898d02bb4e6d31bb60bd3808391144f25eb7bc915597e02109dc2386` |

## 状态说明

平台返回 `harbor_status: evaluation_error`（grader 未能完成评测）。按平台文档，这
不是对答案的判定，可重新提交或联系组织者重新评分。本版本暂不出分，待平台恢复后
跟进。

## 提交内容（本目录）

- `SKILL.md` — Skill 主文档
- `scripts/` — inventory / extract / segment / retrieve / verify / report / audit（旗舰）
- `README.md`、`examples/EXAMPLE.md`（合成演示，非正式案例结果）、`GITHUB_URL.txt`

## 本地验证基线（合成案例，非平台数据）

- 五道 gate 全过（证据 5/5 已校验、契约 6/6 字段完备、status=partial 与 failures
  一致、manifest 哈希一致、日记六阶段覆盖）；status 自动降级逻辑经测试验证。

## 迭代记录

- v1.0.0（2026-11-19）首次提交，评测器执行失败未出分。待重评；代码侧改进方向：
  增加 gate6（answer 中每个事实可指回 evidence 数组）与复跑结果 diff 自动化。
