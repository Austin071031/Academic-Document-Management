# 提交记录（playground submission）

| 项目 | 内容 |
|-|-|
| **Playground Attempt ID** | **89652** |
| 挑战赛 | challenge-2bfd9194（科研资料库与文件管理，玻尔产品周赛第四期） |
| 方向 | 元数据溯源台账（字段字典/多源裁决/冲突留痕） |
| 提交时间 (UTC) | 2026-11-19 08:15 |
| 状态 | pending_review / exec=failed（未评测 · 未收到提交包 bundle missing） |
| 得分 | 0.0（未评测，非终评，score_is_final=false） |
| 查询命令 | `playground status --attempt-id 89652` |

## 版本与提交的对应关系

本目录（版本4-元数据溯源台账）的全部文件与 attempt 89652 打包上传的 skill 内容对应。
每个版本一次 playground 提交，Attempt ID、得分在本文件回填，形成"版本—提交—得分"可追溯链。
映射规则：同一挑战赛下按提交时间顺序对应版本号顺序。全量提交台账见
`../_iteration/01_attempt_registry.md`。

## 执行状态说明

平台返回的原始字段（如实记录，不作结论性判断）：status=pending_review，execStatus=failed，
score=0.0，score_is_final=false。execLog 原文：

> [未评测 · 未收到提交包] 我们没有收到你的提交包（上传未完成），本次没有评分，也不会自动重评。请重新提交。

失败原因与 Skill 内容无关：本次提交使用自行构建的 playground-cli 0.1.7（bundle 协议过旧），
上传接口返回成功但 bundleStatus 停留 incomplete，评测 worker 取包失败。
本题出分提交 88029（**68.6667，终评**）与榜单全部有效成绩均由官方 CLI 0.1.50–0.1.57 提交；
用官方 CLI（≥0.1.57，install.sh 现行 0.1.58）原样重提本版本即可恢复评测。

## 本题当前有效最好成绩

attempt **88029**（2026-11-18 17:05 UTC 提交，scored / final，**68.6667**），
为本题早期基线提交（早于本仓库 版本1–5 建立，内容未纳入仓库版本序列），
评分记录详见 `../_iteration/01_attempt_registry.md`。
