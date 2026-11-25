# SUBMISSION.md — 文献与资料自动分类 v2.1.0

## 提交记录

### attempt 108193（已提交 · 评分排队中）

- 提交时间：2026-11-25（Playground CLI 0.1.58）
- 挑战：challenge-666fefb0 文献与资料自动分类
- 提交内容：v2.1.0 本目录全部文件（SKILL.md + scripts/ + references/ + examples/ + README/CHANGELOG + GITHUB_URL.txt）
- 评测方式：harbor 重放（官方 DeepSeek Harness 在 3 个固定案例上运行本 Skill）
- 状态：`queued`（2026-11-25 提交后复核；出分后回填本记录）
- GitHub 附加分：GITHUB_URL.txt 指向本目录的公开链接（主仓库 Academic-Document-Management）

## 迭代方向

**对照增益证据** —— 聚焦评分维度：使用增益—质量/效率增益与增益可验证性。

父版：v1.0.0（attempt 88926，出分 64.6667，本挑战当时并列第 3）；公共底座继承 v1.1.0
（管理材料整合、可检索索引、引用问答），本版本仅叠加本方向的显著提分改动：

- 新增 baseline_compare.py：同一输入快照模拟基础 Agent 朴素整理（按扩展名平铺、不改名、不去重、不补元数据）
- 与本 Skill 实测按相同口径逐项对比（处置覆盖率、规范命名、元数据填充、重复识别、版本组、人工条目消除）→ gain_report.json/md
- 回写 result.json.gain；契约映射新增 gain/增益/对照 键名

## 本地回归记录（提交前）

合成 17 文件案例（含别名表/版本说明/元数据表/3 问题）全流水线通过；
幂等重跑、一键回滚、validate_output 自查通过；方向特性实测见上。
