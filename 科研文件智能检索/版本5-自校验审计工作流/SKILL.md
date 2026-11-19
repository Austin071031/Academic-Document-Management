---
name: research-doc-audit-workflow
description: 科研文件智能检索——自校验审计工作流。当交付物必须可被第三方独立复核（每条结论有机器校验、每个输出有哈希清单、全过程有留痕、失败如实分类）时使用。旗舰能力：五道交付前自动校验 gate + 追加式运行日记 + 输入输出哈希清单 + 复跑指引。不适用开放网络检索与权限建设。
---

# 科研文件智能检索 · 自校验审计工作流（版本5）

## 1. 用途与触发

检索结果的信任来自**可复核**：评审者要能用记录独立找到同一段原文，要分清"文件没
入库、没有权限、还是检索错了"，要确认没把未完成写成完成。本版本旗舰能力
`audit.py` 在交付前自动执行**五道 gate**，任何一道不过即如实降级：

| gate | 校验内容 | 不过的后果 |
|---|---|---|
| 1 evidence_verified | 保留证据必须 verified=true（quote 逐字存在、页码一致、章节在目录中） | 未校验证据降级或剔除 |
| 2 contract_complete | result.json 含 output_contract 全部字段；必需字段非 null 或有 uncertainty 说明 | 补字段或声明缺失 |
| 3 status_honest | failures 非空时 status≠success；空结果必须有 empty_reason | status 强制降级 |
| 4 manifest_consistent | manifest.json 中每个输出的 sha256 与文件实际一致 | 重算 manifest |
| 5 journal_coverage | run_journal.jsonl 覆盖 盘点→抽取→切分→检索→校验→报告 | 标 partial 并说明缺段 |

配套机制：append-only `run_journal.jsonl`（每操作一条：时间、步骤、输入输出、状态、
失败详情）；`manifest.json`（全部输出的 sha256/大小）；`changes.json`（与上次运行
的差异）；`audit_report.json`（逐 gate 结果、局限声明、复跑命令清单）。

## 2. 运行契约（先读再动）

| 项 | 约定 |
|---|---|
| 案例输入 | `/input/case.json`（`case_id`、`output_contract`）与 `/input/task.md` |
| 工作目录 | `/app/work`（日记与中间产物）；最终输出 `/app/output` |
| 预算 | 64 次模型请求 / 900 秒——审计全脚本化 |

第一步读 case.json/task.md；result.json 原样保留 output_contract 字段与 case_id。

## 3. 定位 Skill 资源

```bash
SKILL=/skills/weekly-skill
[ -f "$SKILL/SKILL.md" ] || SKILL=$(dirname "$(find /skills /app/submission -maxdepth 3 -name SKILL.md 2>/dev/null | head -1)")
```

## 4. 标准工作流

```bash
W=/app/work; O=/app/output; mkdir -p "$W" "$O"
python3 $SKILL/scripts/inventory.py --input-root /input --work-dir $W
python3 $SKILL/scripts/extract.py --input-root /input --work-dir $W
python3 $SKILL/scripts/segment.py --work-dir $W
python3 $SKILL/scripts/retrieve.py --work-dir $W --query "<核心问题>" --topk 10
python3 $SKILL/scripts/verify.py --work-dir $W
python3 $SKILL/scripts/report.py --skeleton --input-root /input --work-dir $W --output-dir $O
# ——阅读 hits.json（只看 verified=true）撰写 answer/summary，设置 status——
python3 $SKILL/scripts/report.py --finalize --input-root /input --work-dir $W --output-dir $O
# 步骤7 【旗舰】五道 gate 审计；不过即降级并写入 audit_report.json
python3 $SKILL/scripts/audit.py --input-root /input --work-dir $W --output-dir $O
```

`audit.py` 会依据 gate 结果自动修正 result.json 的 status（如 gate 不过而写了
success → 强制改 partial），并把 `audit.overall` 与失败 gate 号写入 result.json。

## 5. 失败分类学（failures 数组统一类型）

| type | 含义 | 恢复方式 |
|---|---|---|
| path_missing | 输入根目录不存在 | 报告输入错误，终止 |
| no_permission | 无读取权限 | 排除该文件，请求授权（不绕过） |
| extract_failed / extractor_unavailable | 解析失败/工具缺失 | 换工具或标注 no_text |
| no_text_layer_ocr_unavailable | 扫描件且无 OCR | 如实标注，证据降级 |
| ocr_truncated | OCR 页数截断 | 标注截断范围 |
| legacy_format_unsupported | 旧版二进制 Office | 尝试 antiword/catdoc，否则标注 |
| archive_not_extracted | 压缩包未展开（预算保护） | 如需则手动展开后补跑 |
| empty_file | 零字节文件 | 标注 |
| skipped_by_filter | 被硬条件排除 | 理由写入 filter 审计 |

**不允许把带上述记录的 run 标为 success。**

## 6. 复核路径（第三方如何验证）

1. 打开 `/app/output/result.json` → 每条 evidence 有 file_path/sha256/page/quote；
2. 用 `sha256sum <file>` 核对文件与清单一致（manifest.json）；
3. 按 page 翻到该页，按 quote 逐字比对；
4. 读 `/app/work/run_journal.jsonl` 重现全过程；
5. 按 `audit_report.json.reproduce.steps` 的命令清单在本机复跑；
6. `changes.json` 展示本次运行相对上次的全部变更。

## 7. 异常处置决策表

| 情况 | 处置 |
|---|---|
| 某 gate 失败 | 不删除 gate 结果；修复问题后重跑 audit，日记保留两轮记录 |
| 时间预算将尽 | 立即执行 skeleton+finalize+audit 落盘当前最好结果（partial 也交付） |
| 输出文件损坏 | gate4 捕获 → 重写该文件 → 重算 manifest |
| 无 output_contract | 默认字段集 + uncertainty；gate2 按默认字段校验 |
| 模型无法确定 answer | answer=null + uncertainty 说明已核查到什么程度；status=partial |

## 8. result.json 组装规则

同核心流程，另增要求：`audit` 字段（overall + failed_gates）、`limitations`
（来自 audit_report）、`reproduce` 可复跑说明。answer 只引用 verified 证据；
每处推断与事实分开表述。

## 9. 最小调用示例（示意输出，非正式案例结果）

```bash
python3 $SKILL/scripts/audit.py --input-root /input --work-dir /app/work --output-dir /app/output
# → audit overall=pass
#   gate1 evidence_verified  PASS — 5 evidence, 0 unverified
#   gate2 contract_complete  PASS — fields=6 missing=0
#   gate3 status_honest      PASS — status=partial failures=2
#   gate4 manifest_consistent PASS — outputs=6 mismatch=0
#   gate5 journal_coverage   PASS — core steps covered: 6/6
```

## 10. 不适用情况

联网查新、综述写作、权限建设；审计保证"记录与文件一致"，不保证"检索策略最优"——
策略改进靠其他版本能力（语义对齐/约束过滤/版本谱系）叠加。
