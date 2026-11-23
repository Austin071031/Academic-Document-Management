# 表 2 · 赛题规格（challenge-c050aaed 阅读批注与知识沉淀）

出处：`GET https://play.bohrium.com/api/challenges/challenge-c050aaed`（2026-11-23 实采）。
`rubric_source: official_verified`（页面内容含权重与每维描述，无需自评映射）。

## 任务要求（原文摘句）

> "你需要围绕'阅读批注与知识沉淀'制作一个可被 Agent 调用的 Skill，在组织方提供的 3 个固定科研案例上完成实际任务，并交付能够被复核的结果。"
> "判断本课题是否做对，不看抽了多少页、接了多少模型、写了多少条笔记，而看三件事：批注能否逐条回到原文的具体页与位置；笔记里的每条论断能否指到支撑它的原文片段；沉淀下来的条目能否被真实问题检索到，并被他人按记录复跑核对。"
> "1. 盘点输入文件、目录和权限。2. 按题目规则组织资料并维护元数据/版本关系。3. 输出可检索、可交接的清单或知识结构。4. 记录跳过、失败、冲突和恢复方式。"

## 评分维度与权重（逐行照抄）

| 维度 | 权重 | 评分点 | 考察内容摘句 |
|-|-|-|-|
| 实际效果 | 40 分 | 任务完成度 15；结果正确性 15；结果完整性 5；结果可核验性 5 | "是否把真实阅读材料跑完'批注抽取—笔记结构化—关联—入库'的闭环并交付可用结果"；"批注的原文片段、页码与位置是否与文件一致，笔记论断是否有原文支撑，关联是否有依据"；"是否覆盖材料中各类批注与关键元数据，包括文件类型、元数据字段、目录层级、重复文件、版本差异、权限与来源"；"能否被他人按记录复跑核对" |
| 使用增益 | 25 分 | 质量增益 15；效率增益 5；增益可验证性 5 | "相同材料、相同权限下，加载成果后批注抽取准确率、笔记可用性与关联有效性是否稳定提升"；"人工修改量与返工量是否下降"；"是否通过同输入对照证明质量或效率改善" |
| 创新增益 | 15 分 | 新增能力 5；方法改进 5；创新证据 5 | "基础 Agent 或现有解析工具不具备、或难以稳定实现的能力，例如扫描件批注锚点校正、跨版本批注归并、批注到笔记再到检索的贯通"；"锚点对齐策略、笔记 schema、关联判定规则与检索入口设计是否带来实质改进"；"是否证明创新点相对已有解析工具或基础 Agent 的边界与价值" |
| 可靠体验 | 10 分 | 调用与易用性 3；运行稳定性 4；异常处理 3 | "在给定材料目录时正确触发"；"不同文件类型、页数、版式与重复运行下能否持续产出可用结果"；"对加密或损坏文件、无文本层扫描件、OCR 置信度低、批注来自旧版本、重复文件、权限不足等情况的识别与处置能力" |
| 生态贡献 | 10 分 | 文档完整性 3；资源可复用性 4；分享推广价值 3 | "使用说明、依赖、输入目录约定、输出 schema、示例、边界与维护信息是否齐全"；"脚本、schema、关联规则、题集与金标准能否被他人复用和复跑" |
| GitHub 公开链接 | 附加 5 分 | — | "评审无需登录即可打开链接并找到本次提交的作品，得 5 分" |

评分方式（原文）："综合三个固定案例的实际表现和提交材料评分，各评分项只计一次"；`"strategy":"human_review_only"`；
"平台固定运行 3 个案例，比较不加载 Skill 与加载参赛 Skill 时的实际结果"。

## 提交格式与约束（原文摘句）

> "Create /app/submission/SKILL.md and any required text resources. Use valid name/description YAML frontmatter."
> "The evaluator installs the actual Skill under /skills/weekly-skill, then runs official DeepSeek Harness on each fixed original case."
> "original input is /input/case.json and task.md … Work under /app/work; final actual results and editable artifacts belong under /app/output, including result.json with all original output_contract fields and case_id."
> "Execution budget: 64 model requests, 900 seconds, 16384 tokens per response including reasoning."
> "Skill resources: at most 50 UTF-8 text files, 500KB each and 2MB total, no symlinks."
> "Do not submit prepared answers or formal test outputs."
> "请在提交目录根路径放置 GITHUB_URL.txt，第一行写 GitHub 链接。"

输出要求（每个案例）："保留输入标识、主结果、证据/来源定位、运行状态和不确定性"；
"资料结果：目录、文件清单、元数据、版本关系或知识结构；操作证据：哈希、来源、权限、变更和日志；失败与恢复：跳过、冲突、无权限、重复和恢复记录"。

## 禁做项（原文摘句）

> "不能用预制答案代替实际运行。""Do not fabricate missing software state or scientific data."
> "不依据错误的领域标签补造数据。""材料缺失、无法判断和运行失败要分别说明。"
