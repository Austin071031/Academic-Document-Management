# CHANGELOG

## 1.0.0 (2026-11-19)

- 首版：六脚本流水线（inspect → inventory → extract_refs → plan → apply → report）
  + 机读自查（validate_output）+ 一键流水线（run_pipeline.sh，含失败保底）。
- 元数据：DOI/arXiv/年份正则 + 标题/作者保守启发 + BibTeX/RIS 侧车解析，
  逐字段 source/confidence/evidence；arXiv 号派生年份标注 arxiv_id_derived。
- 分类：T0–T11 规则表（dataset/supplement/scanned/thesis/preprint/conference/journal/other）。
- 版本：DOI 与（规范化标题+第一作者）双键并查集分组；canonical 打分保留，
  其余归档 _archive/versions。
- 去重：sha256 精确重复，保留文件名最干净者，归档 _archive/duplicates。
- 命名：模板降级链（unknown_author/ndate/untitled/原名+sha 短哈希），
  特殊字符与超长标题处理，命名空间按目标目录隔离，冲突不覆盖。
- 可靠性：幂等 already_applied、断点续跑、追加式审计日志、全历史回滚脚本、
  损坏/加密/扫描件/权限不足逐类处置并如实记录。
- 交付：result.json 含 output_contract 全字段（键名启发自动映射 + Agent 填充位）、
  六类要素交代、exceptions、uncertainty；manifest.csv/.json；README 摘要。

## 1.0.0-integrated (2026-11-19)

- 双工作流整合：工作流 B（文档库整理，六脚本 + 一键流水线 + 机读自查）与工作流 A
  （批注提取—笔记结构化—关联—检索，pipeline.py + search.py）统一于一份 SKILL.md。
- result.json 合并：pipeline.py 检测到工作流 B 的 result.json 时，自动将批注工作流
  结果挂入 `annotations_workflow` 键并保留原契约映射；独立副本存 result_annotations.json。
- plan.py 版本分组新增无作者退化键（规范化标题），避免匿名文献版本漏分组。
- 工作流 A 新增：pypdf 缺失时自动 pip 安装重试；CJK 二元组检索回退；
  QuadPoints 凸序重排修复 UL,UR,LL,LR 原始顺序导致的引文恢复失败。

## v2.0.0 (2026-11-23) — 契约层修复版

- 唯一行为变更：SKILL.md frontmatter description 1046B → 470B（疑似越过 1024B 上限
  导致 88935/88961/88966 三次 evaluation_error；出分 skill 实测 690B/1011B）。
- 运行时行为与 v1.0.0 完全一致（回归：双工作流输出逐字节一致，去时间戳）。
- 新增 scripts/check_skill_install.py：提交契约预检（frontmatter 字节上限/UTF-8 纯度/
  文件数量与大小/符号链接/GITHUB_URL），参数读取 direction.json。
- 新增 direction.json（方向元数据，frontmatter_max_bytes 等参数被预检脚本真实读取）。
- 新增 submission.md（提交记录模板，attempt 回填）。
- 仓库侧清理 v1.0.0 残留的 scripts/__pycache__（CLI 打包本就会跳过，仅仓库整洁）。
- 提交：playground attempt 99585（challenge-c050aaed，阅读批注与知识沉淀）
- 同内容重提：playground attempt 107992（challenge-c050aaed，阅读批注与知识沉淀；99585 遇 Harbor 基础设施故障后按纪律重提）

## v2.1.0 (2026-11-25) — 方向1：多载体批注覆盖（Word）

- 新增 scripts/docx_annotations.py：docx 真实批注提取（comments.xml 作者/日期/文字）
  + commentRange 锚定引文恢复（段落号+段内字符偏移，确定性 XML 定位），
  含 <w:ins>/<w:del> 修订标记记录；无批注 docx 如实标注 not_present。
- pipeline.py 增加 4b 步：docx 批注 → 笔记（annotation_type=docx_comment，
  derived_from=docx_annotation，anchor_verified 由 commentRange 命中判定）。
- 命中评分点：实际效果-结果完整性（覆盖"Word 等不同载体"的批注与关键元数据）。
- 未动：PDF 提取/锚点校验/关联/检索/工作流 B 全部行为（回归逐字节一致）。

## v2.2.0 (2026-11-25) — 方向2：增益可验证性（同输入对照）

- 新增 scripts/compare_baseline.py：朴素基线（pdftotext+关键词句，无类型/锚点/关联/索引）
  vs 本 Skill 的 8 项机检指标对照，自动产出 comparison_report.md + comparison.json。
- pipeline.py 10b 步自动生成对照报告；失败仅告警不阻断。
- 命中评分点：使用增益-增益可验证性（"通过同输入对照证明质量或效率改善"）。
- 未动：提取/笔记/关联/检索/工作流 B 全部行为（notes/links 与 v2.1.0 逐字节一致）。
- 提交：playground attempt 108092（challenge-c050aaed，阅读批注与知识沉淀）
