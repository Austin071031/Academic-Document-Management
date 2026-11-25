# Academic-Document-Management — 玻尔周赛赛道主仓库

每个一级目录 = 一道题；题目目录下每个子目录 = 一个版本。

## 版本索引

| 题目 | 版本 | 方向 | 基线关系 | attempt | 状态 | 得分 |
|-|-|-|-|-|-|-|-|
| 阅读批注与知识沉淀 | v1.0.0 | 双工作流一体化（批注沉淀 A + 文档库整理 B） | 首版 | 88935 / 88961 / 88966 | evaluation_error ×3 | evaluation_error |
| 阅读批注与知识沉淀 | v2.0.0 | contract-repair（契约层修复：frontmatter 压缩 + 提交预检） | 基于 v1.0.0 增量 | 99585 | evaluation_error（Harbor 基础设施故障，非终评） | 待出分 |
| 科研知识库问答 | v1.0.0 | 带来源引用的知识库问答 | 首版 | 88927 / 88980 | scored / evaluation_error | 66.0 |
| 文献与资料自动分类 | v1.0.0 | 研究文献库整理策展 | 首版 | 88925 / 88926 | evaluation_error / scored | 64.6667 |
| 科研文件智能检索 | 版本1–5 | 证据锚点/版本谱系/谓词约束/语义对齐/自校验审计 | 方向系列 | — | — | 63.0（88028） |
| 科研资料库与文件管理 | 早期基线（未入库） | 早期提交（内容未纳入仓库版本序列） | 首版 | 88029 | scored（终评） | **68.6667** |
| 科研资料库与文件管理 | 版本1–5 | 哈希账本/内容寻址版本图谱/模板规则引擎/元数据溯源/长期归档 | 方向系列 | 89643/89644/89648/89649/89652/89653 | failed ×6（bundle missing，未评测非终评；CLI 0.1.7 协议过旧，官方 ≥0.1.57 重提可恢复） | 0（未评测） |

## 阅读批注与知识沉淀 · 迭代档案

`阅读批注与知识沉淀/_iteration/`：01_attempt_registry.md（提交台账）/
01_task_spec.md（赛题规格，rubric_source=official_verified）/01_skeleton_diff.md（骨架与白名单）/
00_contract.md（评测契约）/02_scoring_model.md（N=3，评分模型）/03_direction_verdict.md（裁决）/
04_baseline_diagnosis.md（基线诊断）/05_route_cards.md（路线卡）。

## 科研资料库与文件管理 · 迭代档案

`科研资料库与文件管理/_iteration/`：01_attempt_registry.md（提交台账：88029 出分 68.6667 终评 +
版本1–5 六次 bundle missing 失败记录与根因）。各版本目录内含 SUBMISSION.md（版本—提交—得分可追溯链）。
