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
| v2.0.0-案例组件补全 | `科研资料库与文件管理/v2.0.0-案例组件补全/` | 108115 | 2026-11-25 09:10 | submitted（官方 CLI 0.1.58，bundle 状态正常） | 待出分 | — |
| v2.1.0-可核验证据强化 | `科研资料库与文件管理/v2.1.0-可核验证据强化/` | 108117 | 2026-11-25 09:10 | submitted（官方 CLI 0.1.58） | 待出分 | — |
| v2.2.0-元数据正确性强化 | `科研资料库与文件管理/v2.2.0-元数据正确性强化/` | 108118 | 2026-11-25 09:10 | submitted（官方 CLI 0.1.58） | 待出分 | — |
| v2.3.0-检索问答与索引恢复 | `科研资料库与文件管理/v2.3.0-检索问答与索引恢复/` | 108119 | 2026-11-25 09:10 | submitted（官方 CLI 0.1.58） | 待出分 | — |
| v2.4.0-增益证据与生态完备 | `科研资料库与文件管理/v2.4.0-增益证据与生态完备/` | 108120 | 2026-11-25 09:10 | submitted（官方 CLI 0.1.58） | 待出分 | — |

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

## v2.0.0–v2.4.0 迭代说明（2026-11-25 提交）

父辈版本 = attempt 88029（68.6667，本题有效最高分）。丢分诊断与迭代方向：

1. 版本1–5 的 0 分全部是提交通道问题（CLI 0.1.7 bundle 协议过旧），与 Skill 内容无关；v2 系列统一改用官方 CLI 0.1.58 提交，并为每个版本新增 scripts/preflight_check.py 提交契约自检。
2. 对照题面案例画像（real files / aliases / administrative version notes / metadata / **searches/questions / actual recovery/index operations**）逐版本补缺口：v2.0.0 补检索问答+恢复索引两整项；v2.3.0 把这两项做成专精强项。
3. 对照评分细则机检化：v2.1.0 补真实渲染 SVG/PNG 证据图（结果可核验性+创新证据）；v2.2.0 把字段正确性三指标写进 result.json.summary（结果正确性+完整性）；v2.4.0 把使用增益变成前后对照机检计数+幂等证明，并补齐 USAGE/REUSE 生态文档（使用增益 25 + 生态贡献 10）。
