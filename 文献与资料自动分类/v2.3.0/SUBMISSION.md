# SUBMISSION.md — 文献与资料自动分类 v2.3.0

## 提交记录

### attempt 108204（已提交 · 评分排队中）

- 提交时间：2026-11-25（Playground CLI 0.1.58）
- 挑战：challenge-666fefb0 文献与资料自动分类
- 提交内容：v2.3.0 本目录全部文件（SKILL.md + scripts/ + references/ + examples/ + README/CHANGELOG + GITHUB_URL.txt）
- 评测方式：harbor 重放（官方 DeepSeek Harness 在 3 个固定案例上运行本 Skill）
- 状态：`queued`（2026-11-25 提交后复核；出分后回填本记录）
- GitHub 附加分：GITHUB_URL.txt 指向本目录的公开链接（主仓库 Academic-Document-Management）

## 迭代方向

**异常矩阵与极限鲁棒** —— 聚焦评分维度：可靠体验—运行稳定性/异常处理。

父版：v1.0.0（attempt 88926，出分 64.6667，本挑战当时并列第 3）；公共底座继承 v1.1.0
（管理材料整合、可检索索引、引用问答），本版本仅叠加本方向的显著提分改动：

- 新增 robustness.py：六类异常处置矩阵（损坏/加密/扫描件/权限/重复/同名冲突）
- 7 类极限样本端到端自检（截断PDF/伪扩展/空文件/长名/中文名/ZIP伪装PDF），本次实测 6/6 通过 → robustness_report.json
- 回写 result.json.robustness

## 本地回归记录（提交前）

合成 17 文件案例（含别名表/版本说明/元数据表/3 问题）全流水线通过；
幂等重跑、一键回滚、validate_output 自查通过；方向特性实测见上。
