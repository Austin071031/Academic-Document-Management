# 提交说明：research-library-cas-lineage-v2-1（v2.1.0 可核验证据强化）

- 挑战：科研资料库与文件管理（challenge-2bfd9194），Skill 编写任务。
- 基座：版本2-内容寻址版本图谱（v2.0.0）；本版仅做定向增量，基座行为不变。
- 方向：内容寻址对象库 + 版本谱系 DAG + **可核验证据强化**（真实 SVG/PNG
  证据图、对象库恢复与哈希校验、索引重建、提交契约自检）。
- 增量摘要：
  1. `scripts/render_evidence.py` — 纯标准库手写 SVG 证据图（lineage.svg 必出、
     tree_overview.svg），matplotlib optional 渲染 lineage.png，缺失登记不崩溃；
  2. `scripts/recover.py` — sha256 前缀/文件名恢复 + 哈希校验
     （recovery_log.jsonl）+ 索引重建 + 顶层 search_results.json 同步；
  3. `scripts/preflight_check.py` — 提交契约自检 → preflight_report.json；
  4. `references/reproduce.md` — 复跑核对命令清单。
- 命中评分维度：实际效果（结果可核验性：真实渲染图 + 哈希校验恢复）、
  创新增益（创新证据：CAS 谱系 DAG 可视化为 SVG/PNG）、可靠体验（降级不崩溃、
  preflight 自检）、生态贡献（复跑清单）。
- 方法摘要：见 SKILL.md 与 README.md；全部确定性逻辑在 scripts/（Python 标准库，
  matplotlib 仅 optional），Agent 只负责读 case.json、运行流水线、如实转述。
- 自测：合成案例实跑通过（详见 README「自查方法」与 CHANGELOG「自查记录」）。
- 公开链接：GITHUB_URL.txt 第一行（仓库已设为 public，匿名可访问）。

## 成绩记录

| Attempt | 日期 | 得分 | 备注 |
|---|---|---|---|
| 1 | attempt 108117 已提交，出分后回填 | attempt 108117 已提交，出分后回填 | v2.1.0 首次提交 |
| 2 | attempt 108117 已提交，出分后回填 | attempt 108117 已提交，出分后回填 | attempt 108117 已提交，出分后回填 |
| 3 | attempt 108117 已提交，出分后回填 | attempt 108117 已提交，出分后回填 | attempt 108117 已提交，出分后回填 |
