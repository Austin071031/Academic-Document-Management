# SUBMISSION.md — 科研知识库问答 v2.2.0

## 迭代关系

- 父辈版本:v1.0.0(attempt 88927,得分 66.0,评语 "Solid — refine for a more complete and rigorous solution.")
- 本版本方向:六维度元数据与来源溯源
- 变更范围:只改动本方向相关内容,其余与 v1.0.0 一致

## 变更说明

kb_metadata.py 补齐 v1 缺失的两个维度:逐文档 title/authors/year/doi/arxiv(含 confidence,missing 不编造)、来源溯源(路径/duplicate_of/supersedes/mtime);并用行级 diff 量化'版本差异'。

## 目标评分维度

实际效果-结果完整性 5(六维度全覆盖)+ 结果正确性(版本与权限处置):六维度自查表直接映射评分细则。

## 提交记录

- attempt 108106(2026-11-25 提交,Playground CLI 0.1.58,trace=本次迭代会话导出)
- 状态:已入队,等待 harbor 重放评分(得分将回填于此)
- GITHUB_URL.txt 指向:Academic-Document-Management/科研知识库问答/v2.2.0/

## 自测记录(合成资料库,非正式案例)

- 库构造:v1/v2 论文 PDF(版本冲突)、重复备份、管理方说明、损坏 PDF、CSV
- kb 流水线端到端通过;本方向新增脚本实测:kb_metadata 输出 5 文档,4 含非空元数据,v1→v2 版本 diff 统计正常
