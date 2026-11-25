# SUBMISSION.md — 科研知识库问答 v2.3.0

## 迭代关系

- 父辈版本:v1.0.0(attempt 88927,得分 66.0,评语 "Solid — refine for a more complete and rigorous solution.")
- 本版本方向:缺证覆盖证明
- 变更范围:只改动本方向相关内容,其余与 v1.0.0 一致

## 变更说明

kb_coverage.py 为每题生成 coverage_proof:检索词、覆盖文档、锚点规模、被排除文档及原因、verdict_hint;partial_coverage 时禁止下'知识库没有'的强结论,只能降级声明;新增补查义务与冲突矩阵纪律。

## 目标评分维度

实际效果-结果正确性(缺证判断)+ 创新增益 15:把'没有'从主观判断变成可核验的覆盖证明,属基础 Agent 难以稳定实现的能力。

## 提交记录

- attempt 108113(2026-11-25 提交,Playground CLI 0.1.58,trace=本次迭代会话导出)
- 状态:已入队,等待 harbor 重放评分(得分将回填于此)
- GITHUB_URL.txt 指向:Academic-Document-Management/科研知识库问答/v2.3.0/

## 自测记录(合成资料库,非正式案例)

- 库构造:v1/v2 论文 PDF(版本冲突)、重复备份、管理方说明、损坏 PDF、CSV
- kb 流水线端到端通过;本方向新增脚本实测:kb_coverage 输出 2 题覆盖证明,scope=4 canonical docs,excluded=3(旧版本/重复/损坏)
