# 评测契约（§2.4，判死依据）

来源：赛题 API 原文（`official_verified`）+ 基线 v1.0.0 实际文件 + 平台 attempts API。

| 项 | 内容 | 出处 |
|-|-|-|
| Skill 本体 | `/app/submission/SKILL.md` + 文本资源；YAML frontmatter 含合法 name/description | 原文 "Create /app/submission/SKILL.md … Use valid name/description YAML frontmatter" |
| 安装路径 | 评测器把 Skill 安装到 `/skills/weekly-skill` | 原文 "installs the actual Skill under /skills/weekly-skill" |
| 资源限制 | ≤50 个 UTF-8 文本文件；单文件 ≤500KB；总量 ≤2MB；无符号链接 | 原文 "at most 50 UTF-8 text files, 500KB each and 2MB total, no symlinks" |
| description 字节上限 | **实测推断 ≤1024B**：同账号出分 skill 为 690B / 1011B，我们 1046B 三次 evaluation_error | `platform_verified`（01_attempt_registry.md），等级：候选根因 #1（无法从平台直接证实上限数值，标注为强假设） |
| 输入 | `/input/case.json` + `/input/task.md`；材料由题目提供；PDF 为实际文件无预抽取答案层 | 原文 "original input is /input/case.json and task.md" |
| 工作/输出目录 | 中间产物 `/app/work`；最终产物 `/app/output`；必须含 `result.json`（含全部 output_contract 字段 + case_id） | 原文 "final actual results … under /app/output, including result.json with all original output_contract fields and case_id" |
| 预算 | 64 次模型请求 / 900 秒 / 单次响应 16384 token | 原文 "Execution budget: 64 model requests, 900 seconds, 16384 tokens" |
| 诚实约定 | status 如实（success/partial/failed）；sources/uncertainty/change records 必填；缺失、无法判断、运行失败分开说明 | 原文 "Include honest status, sources, uncertainty and change records" |
| 禁做 | 预制答案、编造软件状态或科学数据、按错误领域标签补造数据 | 原文 "Do not submit prepared answers … Do not fabricate … 不依据错误的领域标签补造数据" |
| GitHub 链接 | 提交根路径 `GITHUB_URL.txt`，第一行链接；匿名可访问得 +5 | 原文 "请在提交目录根路径放置 GITHUB_URL.txt" |
| 评测流程 | 固定 3 案例 × 3 重复；基础 Agent vs Skill Agent 对照；human_review_only | 原文 + `"strategy":"human_review_only"` |

## 与 v1.0.0 的对照结论

- 资源文件 22 个文本 / 188KB / 无符号链接 / bundle 内无非 UTF-8 文件 → 合规（bundle 实测，见 01_attempt_registry.md 相关验证）。
- SKILL.md frontmatter description = **1046B > 1024B 疑似上限 → 唯一确认的契约违规候选**。
- 其余契约项（输出路径、result.json 字段、预算内运行、诚实约定、GITHUB_URL.txt）v1.0.0 均已覆盖且本地回归通过。
