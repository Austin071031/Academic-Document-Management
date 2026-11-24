# 表 1 · 提交台账（科研资料库与文件管理）

采集时间：2026-11-24 UTC。来源命令：`playground status --attempt-id {ID}`、`GET /api/attempts/{ID}`、
`GET /api/challenges/challenge-2bfd9194/attempts`。证据等级：platform_verified（平台返回原始字段如实登记，不作结论性外推）。

| 版本 | 目录 | attempt | 提交时间 (UTC) | 状态 | 得分 | score_is_final |
|-|-|-|-|-|-|-|
| 早期提交（未纳入仓库版本序列） | —（bundle 不可下载，内容未入库） | **88029** | 2026-11-18 17:05 | **scored / exec=completed** | **68.6667** | true（终评） |
| 版本1-确定性哈希账本流水线 | `科研资料库与文件管理/版本1-确定性哈希账本流水线/` | 89643 | 2026-11-19 08:14 | pending_review / exec=failed（bundle missing） | 0.0（未评测，非终评） | false |
| 版本1-确定性哈希账本流水线（重提重复件） | 同上 | 89644 | 2026-11-19 08:15 | pending_review / exec=failed（bundle missing） | 0.0（未评测，非终评） | false |
| 版本2-内容寻址版本图谱 | `科研资料库与文件管理/版本2-内容寻址版本图谱/` | 89648 | 2026-11-19 08:15 | pending_review / exec=failed（bundle missing） | 0.0（未评测，非终评） | false |
| 版本3-模板规则引擎归位 | `科研资料库与文件管理/版本3-模板规则引擎归位/` | 89649 | 2026-11-19 08:15 | pending_review / exec=failed（bundle missing） | 0.0（未评测，非终评） | false |
| 版本4-元数据溯源台账 | `科研资料库与文件管理/版本4-元数据溯源台账/` | 89652 | 2026-11-19 08:15 | pending_review / exec=failed（bundle missing） | 0.0（未评测，非终评） | false |
| 版本5-长期归档交付包 | `科研资料库与文件管理/版本5-长期归档交付包/` | 89653 | 2026-11-19 08:15 | pending_review / exec=failed（bundle missing） | 0.0（未评测，非终评） | false |

## 出分提交 88029 的评分记录（platform_verified）

| 字段 | 值 |
|-|-|
| status / execStatus | scored / completed |
| score（终评） | **68.6667**（scoreMax=100，state=final） |
| scorecard | harbor_replay_executed=1, harbor_reward=0.68666667, harbor_score=68.666667, trace_score=null |
| scoringDetails.summary | "Received and graded in full. Solid — refine for a more complete and rigorous solution." |
| 提交方式 | 官方 Playground CLI 0.1.57（detail: "Submitted by @paper2arm/playground-cli 0.1.57."） |
| harness | harbor-lbg |

版本对应关系说明（如实记录）：88029 提交于 2026-11-18 17:05 UTC，早于本仓库 版本1–5 的建立时间
（2026-11-19）；其 bundle 在平台侧已不可下载（bundlePath=null），提交内容未纳入本仓库版本序列。
按"同一挑战赛下按提交时间顺序对应版本号顺序"的映射规则，88029 记为本题**早期基线提交**，
版本1–5 为其后的五方向迭代系列；本题当前有效最好成绩为 **68.6667（attempt 88029，终评）**。

## 版本1–5 失败原因（platform_verified）

6 个 attempt（含 89643/89644 重复件）execLog 均为同一原文：

> [未评测 · 未收到提交包] 我们没有收到你的提交包（上传未完成），本次没有评分，也不会自动重评。请重新提交。
> [Not evaluated - bundle missing] Your submission bundle never reached the evaluation worker, so nothing was scored. Please re-submit.

对照事实：

- 版本1–5 提交时使用的是从开源仓库源码自行构建的 playground-cli **0.1.7**（bundle 协议过旧），
  上传接口返回成功（scorecard executability/packaging/trace_quality 均=1），但 bundleStatus 停留在
  `incomplete`，评测 worker 取包失败。
- 出分的 88029 与榜单上全部有效成绩（59.33–73.0）均由官方发布版 CLI 0.1.50–0.1.57 提交
  （install.sh 现行版本 0.1.58，https://play.bohrium.com/install.sh）。

判读：失败与 Skill 内容无关，纯属提交通道协议不匹配；用官方 CLI（≥0.1.57）原样重提版本1–5 即可恢复评测。
