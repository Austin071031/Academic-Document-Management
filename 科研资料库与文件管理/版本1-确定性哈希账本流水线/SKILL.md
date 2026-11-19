---
name: research-library-ledger-pipeline-v1
description: 确定性哈希账本流水线，用于整理乱序科研资料库——递归盘点流式 sha256、去重、版本链、按项目/年份/类型归位到 library/ 并出具可独立复跑核对的 manifest 与 verify 报告；当任务要求对 /input 下含中文名、改名副本、历史版本、管理备注、压缩包的科研文件进行盘点、组织、去重、版本判定与可审计交付时触发。
---

# 科研资料库与文件管理 · 版本1：确定性哈希账本流水线

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

**step2（Agent 补叙述）**：编辑 /app/output/result.json：把 `_pending_fields` 中各字段填成基于产物的结论（引用 manifest.json / duplicates.json / versions.json 中的具体数字与路径）；若 case.json 含 searches/questions，把回答写入相应字段；把额外不确定性追加进 `uncertainty`。不要把无出处猜测写进元数据字段。

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

## ⑤ 不适用边界与限制

- 版本相似度基于文件名归一化 stem 的 difflib（阈值 0.75）+ mtime 排序，不解析文件内容语义；对完全改名的版本可能漏判，需在 uncertainty 声明。
- 伴随表 join 依赖 stem 匹配（精确或子串），表格结构过于自由时字段保持 null+原因。
- 仅标准库；不联网；不调用任何外部模型。64 请求/900 秒预算内脚本占 0 请求。
- 单文件 >500MB 可读但不入库的场景不受支持（仍会计入账本并尝试复制）。
- 账本为单次 scan 全量重生成（幂等优先于追加历史），append-only 语义体现在单次日志/账本行不可变。
