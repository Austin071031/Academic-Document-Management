# 提交说明：research-library-rule-engine-v2-4

- 挑战：科研资料库与文件管理（challenge-2bfd9194），Skill 编写任务。
- 方向：声明式模板+规则引擎归位（基座：版本3）+ v2.4.0 可机检增益证据（前后对照/幂等验证）与生态完备文档。
- 方法摘要：见 SKILL.md 与 README.md；全部确定性逻辑在 scripts/（Python 标准库），Agent 只负责读 case.json、运行流水线、补 result.json 叙述字段。
- 自测：合成案例实跑通过（详见 README「自查方法」与 CHANGELOG）。
- 公开链接：GITHUB_URL.txt 第一行（仓库已设为 public，匿名可访问）。
