# 版本5 · 自校验审计工作流 — 使用与方法说明

## 这个版本解决什么问题

检索交付要能被第三方独立复核：每条结论有机器校验、每个输出有哈希清单、全过程
留痕、失败如实分类。本版本以**五道交付 gate** 为核心，把"可复核"做成强制流程
而不是文字承诺。

## 五道 gate

1. **evidence_verified**：保留证据必须 verified=true（quote 逐字存在、页码一致、
   章节在目录中）；
2. **contract_complete**：result.json 含 output_contract 全部字段，必需字段非 null
   或有 uncertainty 说明；
3. **status_honest**：failures 非空时 status≠success；空结果必须有 empty_reason；
4. **manifest_consistent**：输出清单 sha256 与文件实际一致；
5. **journal_coverage**：run_journal.jsonl 覆盖 盘点→抽取→切分→检索→校验→报告。

gate 不过 → 自动降级 status 并把 failed_gates 写入 result.json；**不删除 gate
结果**，修复后重跑，日记保留全部轮次。

## 审计产物

| 文件 | 内容 |
|---|---|
| /app/work/run_journal.jsonl | append-only 操作日记（时间/步骤/输入输出/状态/失败详情） |
| /app/output/manifest.json | 全部输出文件的 sha256 与大小 |
| /app/output/changes.json | 与上次运行的输出差异（变更记录） |
| /app/output/audit_report.json | 逐 gate 结果、局限声明、复跑命令清单 |

## 失败分类学

path_missing / no_permission / extract_failed / extractor_unavailable /
no_text_layer_ocr_unavailable / ocr_truncated / legacy_format_unsupported /
archive_not_extracted / empty_file / skipped_by_filter——统一写入 failures 数组，
**带任一失败的 run 不得标 success**。

## 第三方复核路径

result.json 证据 → sha256sum 核对 → 按 page 翻页按 quote 逐字比对 →
run_journal.jsonl 重现过程 → 按 audit_report.reproduce.steps 复跑 →
changes.json 查看变更。

## 依赖与安装

- Python ≥3.9（仅标准库）；无网络依赖。安装＝复制到 `/skills/weekly-skill`。

## 目录约定

```
scripts/audit.py      【旗舰】五道 gate + 报告（步骤7）
scripts/{inventory,extract,segment,retrieve,verify,report}.py  核心流水线
```

## 运行示例

见 `SKILL.md` 第 4、9 节；合成演示见 `examples/EXAMPLE.md`（标注为示例）。

## 限制与失败处理

- 审计保证"记录与文件一致"，不保证"检索策略最优"；策略改进靠语义对齐/约束过滤/
  版本谱系等能力叠加；
- 时间预算将尽时立即 skeleton+finalize+audit 落盘当前最好结果（partial 也交付）。

## 维护

gate 集合在 `audit.py:run_gates()` 中定义；新增检查需同步 SKILL.md 与本说明。
