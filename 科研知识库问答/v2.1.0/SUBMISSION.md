# SUBMISSION.md — 科研知识库问答 v2.1.0

## 迭代关系

- 父辈版本:v1.0.0(attempt 88927,得分 66.0,评语 "Solid — refine for a more complete and rigorous solution.")
- 本版本方向:证据机器核验
- 变更范围:只改动本方向相关内容,其余与 v1.0.0 一致

## 变更说明

kb_verify.py 对每条 evidence 逐字比对 exact_quote(空白归一),自动修齐为原文精确子串并回填 page/para_index/char 偏移与 sha256_16;verified=false 的证据禁止提交。

## 目标评分维度

实际效果-结果正确性 15 + 可核验性 5:引用真实性与坐标精度由机器保证,verify_report.json 随包交付支撑独立复核。

## 提交记录

- attempt 108105(2026-11-25 提交,Playground CLI 0.1.58,trace=本次迭代会话导出)
- 状态:已入队,等待 harbor 重放评分(得分将回填于此)
- GITHUB_URL.txt 指向:Academic-Document-Management/科研知识库问答/v2.1.0/

## 自测记录(合成资料库,非正式案例)

- 库构造:v1/v2 论文 PDF(版本冲突)、重复备份、管理方说明、损坏 PDF、CSV
- kb 流水线端到端通过;本方向新增脚本实测:kb_verify 对 1 条证据自动修齐(空白差异回填坐标),0 条未通过
