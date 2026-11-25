# SUBMISSION.md — 文献与资料自动分类 v1.1.0

## 提交记录（按时间）

### attempt 108052（已提交 · 评分排队中）

- 提交时间：2026-11-25 08:53 UTC（Playground CLI 0.1.58）
- 挑战：challenge-666fefb0 文献与资料自动分类
- 提交内容：v1.1.0 本目录全部文件（SKILL.md + 12 脚本 + 5 份 references + 示例 + README/CHANGELOG + GITHUB_URL.txt）
- 评测方式：harbor 重放（官方 DeepSeek Harness 在 3 个固定案例上运行本 Skill）
- 状态：`queued`（2026-11-25 复核；出分后回填本记录）
- GitHub 附加分材料：`GITHUB_URL.txt` 指向
  https://github.com/Austin071031/Literature-Management-Skill-Auto-Classification-of-Documents-Materials
  （公开可匿名访问，与本目录内容一致）

## 相对 v1.0.0（64.67 分）的变更

针对隐藏案例工单中的"别名、管理性版本说明、元数据、检索/问答、恢复/索引操作"缺口：

1. **管理性材料整合**（admin_notes.py + plan.py）：解析别名表/版本说明/元数据表，
   指令优先于启发式；原件归档 `_archive/admin/` 不入库。
2. **可检索索引**（kb_index.py）：按页切块 + 倒排索引，块级坐标（文件/页码/块号）回链。
3. **带引用问答**（kb_search.py + answer_questions.py）：BM25 + 中英同义双向扩展；
   低于阈值如实回答"未找到依据"，禁止编造。
4. frontmatter description 压缩至 913B（≤1024B，规避安装期 evaluation_error 风险）。

## 本地回归记录（提交前）

合成 17 文件案例（10 材料 + 别名表 + 版本说明 + 元数据表 + 3 问题）：
元数据表补缺 2 文件；authoritative 指令正确覆盖 canonical；3 问中 2 问命中目标文献、
1 问（库中不存在的主题）如实 no_evidence；幂等重跑 15 条 already_applied；
validate_output 自查通过；一键回滚后目录清空。
