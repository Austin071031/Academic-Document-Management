---
name: research-library-ledger-pipeline-v2-0
description: 确定性哈希账本流水线 v2，整理乱序科研资料库——递归盘点 sha256、去重、版本链、按项目/年份/类型归位 library/ 并出具可复跑核对的 manifest 与 verify 报告；v2 补全案例组件：检索问答（倒排索引+行号片段证据）与恢复/重建索引（按文件名/哈希/别名从账本、压缩包展开或源备份恢复并校验）。当 /input 案例要求组织资料库、回答检索问题、从别名/备份/压缩包恢复文件或重建索引并满足 output_contract 时触发。
---

# 科研资料库与文件管理 · v2.0.0：案例组件补全（基座=版本1 确定性哈希账本流水线）

## ① 触发与适用条件

**适用**：/input 下是"乱糟糟的科研资料库"——含中文与特殊字符文件名、改名备份副本（别名）、管理性版本备注 CSV/md、伴随元数据表、zip/tar 压缩包、深层目录、不可读文件、内容相同但名字不同的重复文件、同一文档多个历史版本；要求把产物放入 /app/output（含 result.json），并满足 output_contract。

**不适用**：需要联网检索数据库元数据、需要人工策展式判断、文件量超过单机内存账本的场景（见 ⑤）。

## ② 执行协议

**step0（先存诚实结果）**：检查 /input 清单（`ls -laR /input | head`），然后立即运行
`python3 scripts/write_partial_result.py --input /input --work /app/work --output /app/output`
生成 partial result.json（status=partial，逐项占位 output_contract 字段）。

**step1（跑流水线）**：
```bash
python3 scripts/library_pipeline.py --input /input --work /app/work --output /app/output
```
等价于 scan→plan→apply→write_partial_result→report→verify 全链路。确定性工作全在脚本内，不消耗模型请求。
若某子步骤需单独重跑：`python3 scripts/library_pipeline.py <scan|plan|apply|report|verify> --input ... --work ... --output ...`。

**step1b（案例组件：恢复/检索，全链路末尾已自动衔接）**：上一步全链路结束时，若 case.json 含 recovery/recover/restore 类任务会自动调用 recover.py（逐条恢复，写 recovery_log.jsonl）；含 searches/questions/queries 会自动调用 qa.py（写 search_results.json），随后自动重跑 verify。如需手动执行/补充：
```bash
# 恢复单个目标（文件名 / sha256 前缀 / 别名），可指定 library/ 内落点
python3 scripts/recover.py --input /input --work /app/work --output /app/output \
    --target "关键词或sha256前缀" [--restore-to "项目/年份/类型/文件名"]
# 重建 manifest 与检索索引并重跑 verify
python3 scripts/recover.py --input /input --work /app/work --output /app/output --rebuild-index
# 手动跑检索问答（读 case.json 的 searches/questions）或临时单条查询
python3 scripts/qa.py --input /input --work /app/work --output /app/output [--query "关键词"]
```
recover/qa 幂等（同哈希目标记 already_present 不覆盖；索引整本重建），失败记账不崩溃。恢复完成后务必再跑一次 step3 的 verify 并在 step2 叙述中引用 recovery_log.jsonl / search_results.json 的具体条目。

**step2（Agent 补叙述）**：编辑 /app/output/result.json：把 `_pending_fields` 中各字段填成基于产物的结论（引用 manifest.json / duplicates.json / versions.json 中的具体数字与路径）；若 case.json 含 searches/questions，把 search_results.json 中对应回答（含命中 文件:行号 证据；no_evidence 须如实说明缺什么）写入相应字段；若有 recovery 任务，把 recovery_log.jsonl 的来源/依据/恢复路径/sha256 校验结果写入相应字段；把额外不确定性追加进 `uncertainty`。不要把无出处猜测写进元数据字段。

**step3（verify 写回）**：
```bash
python3 scripts/library_pipeline.py verify --input /input --work /app/work --output /app/output
```
把 verify_report.json 的 verdict 与 totals 摘要进 result.json 的叙述（或交由 step4 自动合并）。

**step4（finalize + 校验）**：
```bash
python3 scripts/finalize_result.py --input /input --work /app/work --output /app/output
python3 scripts/validate_result.py --input /input --output /app/output
```
finalize 会用 verify 结论自动修正 status（PASS→success）；validate 退出码必须为 0。

## ③ 输出清单（/app/output）

| 文件 | 内容 |
|---|---|
| `library/` | 按 `项目/年份/数据类型/` 组织的文件树（复制，不移动） |
| `manifest.json` / `manifest.csv` | 每文件元数据，字段带 source+evidence，缺失为 null+原因 |
| `duplicates.json` | 内容 sha256 精确重复组（canonical/aliases） |
| `versions.json` | 版本链（difflib 相似度 + mtime 序列），含 superseded_by |
| `operation_log.jsonl` | append-only 操作日志（before/after/sha256/action/time） |
| `verify_report.json` | library 重哈希比对（match/mismatch/missing/extra + 总计 + verdict） |
| `inventory.jsonl` / `plan.json` | 账本与方案的审计副本，供独立复跑 |
| `search_results.json` | v2：searches/questions 每条回答，命中带 文件路径+行号+原文片段 证据；无命中 no_evidence+缺口说明 |
| `recovery_log.jsonl` | v2：恢复/重建索引操作日志（来源、依据、恢复路径、sha256 校验），append-only |
| `result.json` | case_id + output_contract 全部字段 + status/sources/uncertainty/change_records |

## ④ 异常处理对照表

| 情况 | 处置 |
|---|---|
| 上传中断/部分文件缺失 | 重跑 `scan` 幂等（账本整本重生成）；verify 报 missing 并 FAIL |
| 权限不足/不可读 | inventory 记 `readable=false`+原因；apply 记 `skip_unreadable`；算"跳过"不算"完成"；写入 uncertainty |
| 重名冲突 | plan 阶段确定性分配 `__dupN` 后缀，绝不覆盖 |
| 哈希不符 | verify 记 `mismatch` 并 FAIL，写入 result.uncertainty |
| 元数据缺失 | 字段置 null 并注明抽取失败原因（source 记录实际尝试过的来源），绝不猜 |
| 损坏 zip/tar | 按普通文件登记并记 `archive_error`；合法成员安全展开（防路径穿越）并登记为 archive_member |
| 零字节文件 | 不参与去重（避免误并不相关空文件），在 duplicates.json 单独列出 |
| 恢复目标找不到 | recovery_log 记 `not_found`+已查来源清单，result.uncertainty 声明，绝不伪造 |
| 恢复落点已存在 | 同哈希记 `already_present` 不覆盖；异哈希确定性 `__dupN` 重命名 |
| 检索无命中 | search_results.json 记 `no_evidence`+缺口原因（未入库/非文本/措辞差异），绝不编答案 |

## ⑤ 不适用边界与限制

- 版本相似度基于文件名归一化 stem 的 difflib（阈值 0.75）+ mtime 排序，不解析文件内容语义；对完全改名的版本可能漏判，需在 uncertainty 声明。
- 伴随表 join 依赖 stem 匹配（精确或子串），表格结构过于自由时字段保持 null+原因。
- v2 检索问答为字面/词项级匹配（中文 bigram 兜底），无语义理解；pdf/docx 等二进制正文不解析，相关查询会诚实 no_evidence。
- v2 恢复以来源存在为前提（源备份/压缩包展开/同哈希组成员三者全无时记 not_found）；恢复目标是"内容复原+证据记账"，不推断业务语义。
- 仅标准库；不联网；不调用任何外部模型。64 请求/900 秒预算内脚本占 0 请求。
- 单文件 >500MB 可读但不入库的场景不受支持（仍会计入账本并尝试复制）。
- 账本为单次 scan 全量重生成（幂等优先于追加历史），append-only 语义体现在单次日志/账本行不可变。
