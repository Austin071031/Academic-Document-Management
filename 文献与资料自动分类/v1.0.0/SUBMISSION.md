# SUBMISSION.md — 文献与资料自动分类 v1.0.0

## 提交记录（按时间）

### attempt 88926（已出分 · 64.67 / 100）

- 提交时间：2026-11-19 02:48 UTC（Playground CLI 0.1.57）
- 最终评分时间：2026-11-19 14:30 UTC
- 挑战：challenge-666fefb0 文献与资料自动分类
- 提交内容：v1.0.0 本目录全部文件（SKILL.md + 8 脚本 + 5 份 references + 示例 + README/CHANGELOG）
- 评测方式：harbor 重放（官方 DeepSeek Harness 在 3 个固定案例上运行本 Skill）
- 得分构成：`harbor_reward = 0.64666667`，`harbor_replay_executed = 1`，`trace_factor = 1.0`，`harbor_errors = 0`
- 评语："Received and graded in full. Solid — refine for a more complete and rigorous solution."
- 声明标签：model = SciMaster，harness = SciMaster agent harness
- 说明：该包未包含 `GITHUB_URL.txt`（GitHub 附加分未计入本分数；附加分与 100 分主评分独立）
- 数据来源：GET /api/attempts/88926（2026-11-25 复核）

### attempt 88925（evaluation_error，未出分）

- 提交时间：2026-11-19 02:48 UTC
- 提交内容：与 88926 相同
- 状态：`failed`（harbor 评测运行失败，`harbor_errors = 0`、replay 已执行但无 reward，
  非对答案质量的判定；同一小时窗口内同账号其他提交有成功有失败，判定含瞬时 worker 故障分量）

### attempt 88967（evaluation_error，未出分）

- 提交时间：2026-11-19 03:21 UTC
- 提交内容：与 88926 相同 + 根目录 `GITHUB_URL.txt`（指向 GitHub 作品链接）
- 状态：`failed`（同上，evaluation_error，未获得评分）

## 基线参照

- 组织方 canary（官方 Harness 作者 Skill，attempt 66905）：64.6667 分
- 本版本得分与 canary 持平（64.6667 vs 64.6667）

## v1.0.0 已知不足（v1.1.0 已修复）

1. 未处理案例随附的**管理性材料**（别名表、管理性版本说明、元数据表），
   版本/命名决策仅依赖启发式。
2. 无**可检索索引与带引用的问答**能力：案例工单包含 searches/questions 与
   recovery/index 操作要求，v1.0.0 未覆盖。
3. 两次 evaluation_error（88925、88967）提示重放存在瞬时故障分量；
   frontmatter description 实测 1011B，接近 1024B 上限，v1.1.0 已压缩至 913B。
