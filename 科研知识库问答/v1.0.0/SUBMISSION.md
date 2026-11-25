# SUBMISSION.md — 科研知识库问答 v1.0.0

## 提交记录（按时间）

### attempt 88927（已出分 · 66.0 / 100）

- 提交时间：2026-11-19 02:51 UTC（Playground CLI 0.1.57）
- 最终评分时间：2026-11-19 15:02 UTC
- 挑战：challenge-80dd5ddc 科研知识库问答
- 提交内容：v1.0.0 本目录全部文件（SKILL.md + 6 脚本 + 3 份 references + 示例 + README）
- Bundle SHA-256：7562fba18ec9a19c9c7484d39bdea6b2261d196d407c8718a159b78c33aeaebc
- 评测方式：harbor 重放（官方 DeepSeek Harness 在 3 个固定案例上运行本 Skill）
- 得分构成：`harbor_reward = 0.66`，`harbor_replay_executed = 1`，`trace_factor = 1.0`，`harbor_errors = 0`
- 评语："Received and graded in full. Solid — refine for a more complete and rigorous solution."
- 声明标签：model = SciMaster，harness = SciMaster
- 说明：该包未包含 `GITHUB_URL.txt`（GitHub 附加分未计入本分数；附加分与 100 分主评分独立）

### attempt 88980（evaluation_error，未出分）

- 提交时间：2026-11-19 03:3x UTC
- 提交内容：与 88927 相同 + 根目录 `GITHUB_URL.txt`（指向 GitHub 作品链接）
- Bundle SHA-256：b04f3d04303cf1daa477f28bdbdd80b974dbeda438925b003ccd2703b7fdfd5d
- 状态：`evaluation_error`（平台评测运行失败，`harbor_errors = 0`，非对答案质量的判定，可联系组织方重判或重新提交）

## 基线参照

- 组织方 canary（官方 Harness 内置 Skill，attempt 66907）：58.67 分
- 本版本相对基线提升：+7.33 分（66.0 vs 58.67）

## 后续迭代方向（v1.0.0 已知不足）

1. 得分 66.0 低于目标 80 分；评语指向"完整性与严谨性"，下一步应结合评测日志分析 3 个案例中 result.json 合同字段覆盖与证据坐标精度。
2. 88980 的 evaluation_error 需复查（同类报告见社区 topic 49/52/53/55/56，"fast-fail" 可能与提交路径/标签相关）。
3. GitHub 附加分（+5）尚未在任何出分提交中生效，需将 `GITHUB_URL.txt` 并入下一次提交。
