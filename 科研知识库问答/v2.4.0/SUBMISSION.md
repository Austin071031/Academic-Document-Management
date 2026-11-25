# SUBMISSION.md — 科研知识库问答 v2.4.0

## 迭代关系

- 父辈版本:v1.0.0(attempt 88927,得分 66.0,评语 "Solid — refine for a more complete and rigorous solution.")
- 本版本方向:证据打包与预算治理
- 变更范围:只改动本方向相关内容,其余与 v1.0.0 一致

## 变更说明

kb_pack.py 将全部问题的命中去重合并为单文件证据包,模型阅读轮次降为 1;硬性预算表(≤8 次模型请求)+ 增量保盘点(每题答完即合成)+ pack_report 使效率增益可验证。

## 目标评分维度

使用增益 25:减少检索轮次与人工核对条目;增益可验证性由 pack_report.json 与 ops_log 支撑;降低 900 秒预算内烂尾概率。

## 提交记录

- attempt 108114(2026-11-25 提交,Playground CLI 0.1.58,trace=本次迭代会话导出)
- 状态:已入队,等待 harbor 重放评分(得分将回填于此)
- GITHUB_URL.txt 指向:Academic-Document-Management/科研知识库问答/v2.4.0/

## 自测记录(合成资料库,非正式案例)

- 库构造:v1/v2 论文 PDF(版本冲突)、重复备份、管理方说明、损坏 PDF、CSV
- kb 流水线端到端通过;本方向新增脚本实测:kb_pack 生成单文件证据包(2 题,一次读取),pack_report 记录命中与字符数
