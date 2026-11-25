# SUBMISSION — 版本2-版本谱系图谱

| 字段 | 内容 |
|---|---|
| 题目 | 科研文件智能检索（challenge-139745c7，玻尔产品周赛第四期） |
| 方向 | 版本谱系图谱：哈希去重 + 内容相似度版本链 + 副本/改名/修订角色判定 + 版本感知检索 |
| Attempt ID | [89366](https://play.bohrium.com/attempt/89366) |
| 提交时间 | 2026-11-19 07:33 UTC |
| 评测状态 | **scored（final）** |
| 得分 | **68.6667 / 100（本系列五版当前最高）** |
| Outcome | partial |
| 评测摘要 | "Received and graded in full. Solid — refine for a more complete and rigorous solution." |
| Bundle SHA-256 | `4c0a7a9bab507ac402bb780ae779d7d332970c944ee07a62823dbd198a7df20f` |

## 提交内容（本目录）

- `SKILL.md` — Skill 主文档
- `scripts/` — inventory / extract / segment / lineage（旗舰）/ retrieve / verify / report
- `README.md`、`examples/EXAMPLE.md`（合成演示，非正式案例结果）、`GITHUB_URL.txt`

## 本地验证基线（合成案例，非平台数据）

- 改名副本（哈希级重复）正确归为 `renamed_copy` 并入 `exclude_sha256`；
- 版本感知检索只返回 canonical 命中；verify 5/5 通过。

## 迭代记录

- v1.0.0（2026-11-19）首次提交，得分 68.6667。后续改进方向：提高修订链召回
  （短文档 shingle 稀疏时补 token 级回退比对），并在证据中显式给出版本差异
  （两版对应段落锚点对）以加强"版本比较"类问题的回答质量。
