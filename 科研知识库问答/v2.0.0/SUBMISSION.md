# SUBMISSION.md — 科研知识库问答 v2.0.0

## 迭代关系

- 父辈版本:v1.0.0(attempt 88927,得分 66.0,评语 "Solid — refine for a more complete and rigorous solution.")
- 本版本方向:一键管线 + 交付自检
- 变更范围:只改动本方向相关内容,其余与 v1.0.0 一致

## 变更说明

kb_run.py 将 v1 九阶段收敛为三步,阶段 0 即写 result.json 骨架;kb_selfcheck.py 七项硬检查(case_id/合同字段/证据真实性/编号互洽/缺证声明/冲突 resolution/日志状态一致),退出码非 0 不得结束。

## 目标评分维度

实际效果-任务完成度 15 + 可靠体验 10:杜绝 Agent 漏步骤、超时空手、result.json 缺字段;自检报告本身即运行稳定性证据。

## 提交记录

- attempt 108104(2026-11-25 提交,Playground CLI 0.1.58,trace=本次迭代会话导出)
- 状态:已入队,等待 harbor 重放评分(得分将回填于此)
- GITHUB_URL.txt 指向:Academic-Document-Management/科研知识库问答/v2.0.0/

## 自测记录(合成资料库,非正式案例)

- 库构造:v1/v2 论文 PDF(版本冲突)、重复备份、管理方说明、损坏 PDF、CSV
- kb 流水线端到端通过;本方向新增脚本实测:kb_run 三步流程产出 result.json 骨架+预填 answers(2 题,含命中候选);kb_selfcheck 七项全过退出码 0
