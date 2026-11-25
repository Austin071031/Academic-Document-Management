# SUBMISSION — 版本4-语义对齐检索

| 字段 | 内容 |
|---|---|
| 题目 | 科研文件智能检索（challenge-139745c7，玻尔产品周赛第四期） |
| 方向 | 语义对齐检索：中英/同义/上下位对照词表 + 语料缩写自动抽取，查询双向展开的概念级索引 |
| Attempt ID | [89373](https://play.bohrium.com/attempt/89373) |
| 提交时间 | 2026-11-19 07:44 UTC |
| 评测状态 | **pending_review（evaluation_error，未出分）** |
| 得分 | —（平台评测器执行失败，非答案判定） |
| Bundle SHA-256 | `40cbe01eae449b369bf3b0488e963aea363f3c9dc18cf9f0ee0d91925bd62c28` |

## 状态说明

平台返回 `harbor_status: evaluation_error`（grader 未能完成评测）。按平台文档，这
不是对答案的判定，可重新提交或联系组织者重新评分。本版本暂不出分，待平台恢复后
跟进。

## 提交内容（本目录）

- `SKILL.md` — Skill 主文档
- `scripts/` — inventory / extract / segment / concepts（旗舰）+ aliases.txt / retrieve / verify / report
- `README.md`、`examples/EXAMPLE.md`（合成演示，非正式案例结果）、`GITHUB_URL.txt`

## 本地验证基线（合成案例，非平台数据）

- 概念映射 218 组（人工词表 50+ 条 + 自动缩写抽取）；查询"缓冲液 配方"经别名
  扩展同时命中中英文档；verify 5/5 通过。

## 迭代记录

- v1.0.0（2026-11-19）首次提交，评测器执行失败未出分。待重评；代码侧改进方向：
  概念索引按段落→章节两级聚合减少冗余命中，多义词消歧增加上下文窗口特征。
