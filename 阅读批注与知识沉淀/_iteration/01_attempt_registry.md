# 表 1 · 提交台账（阅读批注与知识沉淀）

采集时间：2026-11-23 UTC。来源命令：`playground status --attempt-id {ID}`、`GET /api/attempts/{ID}`（§0-10）。

| 版本 | 目录 | 方向（direction.json） | attempt | 提交时间 | 状态 | 得分 | 置信度 |
|-|-|-|-|-|-|-|-|-|
| v1.0.0 | `阅读批注与知识沉淀/v1.0.0/` | 无 direction.json（v1.0.0 未引入方向元数据；方向 = 双工作流一体化，见 SKILL.md） | 88935 | 2026-11-19 03:03 | pending_review / exec=failed / harbor=evaluation_error | 0（evaluation_error，非终评，score_is_final=false） | platform_verified |
| v1.0.0 | 同上 | 同上 | 88961 | 2026-11-19 03:13 | pending_review / exec=failed / harbor=evaluation_error | 0（同上） | platform_verified |
| v1.0.0 | 同上 | 同上 | 88966 | 2026-11-19 03:19 | pending_review / exec=failed / harbor=evaluation_error | 0（同上） | platform_verified |

补充事实（同账号同 CLI 同 harness=harbor-lbg，用于定位故障性质，证据等级均为 platform_verified）：

| attempt | 题目 | 提交时间 | 结果 |
|-|-|-|-|
| 88926 | 文献与资料自动分类 | 2026-11-19 02:48 | scored 64.6667（其 SKILL.md description 实测 1011B） |
| 88925 | 文献与资料自动分类 | 2026-11-19 02:48 | evaluation_error |
| 88927 | 科研知识库问答 | 2026-11-19 02:51 | scored 66.0（description 实测 690B） |
| 88980 | 科研知识库问答 | 2026-11-19 03:29 | evaluation_error |
| 88968/88970 | 其他题目 | 03:21/03:22 | scored |
| 88977/88978 | 其他题目 | 03:27/03:27 | evaluation_error |
| 89083 等 20 人 | 本题 challenge-c050aaed | 11-17 至 11-21 | 全部 scored（公开 attempts 列表，59.33–71.67） |

判读：
1. 失败与成功在同一小时窗口内交错出现 → 存在**瞬时 worker 故障**分量，重提可自愈。
2. 本题我们 3/3 全败且同账号出分 skill 的 description 均 ≤1011B、我们为 **1046B** → **1024 字节上限**是最可疑的可控内容因素（零风险可修复）。
3. 仓库 v1.0.0 内无 submission.md / direction.json（v1.0.0 未建立该元数据），台账行据平台复核直接登记。
