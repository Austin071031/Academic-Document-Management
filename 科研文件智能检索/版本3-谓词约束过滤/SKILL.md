---
name: research-doc-constraint-filter
description: 科研文件智能检索——谓词约束过滤引擎。当任务带硬条件（年份、项目编号、文件类型、实验批次、版本、权限、目录范围）且要求"严格按条件筛、不满足就如实报告、绝不放宽"时使用。旗舰能力：把任务文本编译为强类型谓词、逐谓词执行与计数、冲突诊断报告。不适用开放网络检索与权限建设。
---

# 科研文件智能检索 · 谓词约束过滤（版本3）

## 1. 用途与触发

检索任务常带硬约束："只要 2020–2025 的 PDF""只看某项目编号下的实验记录""只要最新版"。
典型失败是**静默放宽**（条件不满足时偷偷扩大范围）或**误报无结果**（其实是解析错了
条件）。本版本旗舰能力 `constraints.py` 把任务文本**编译为强类型谓词**并严格执行：

- 每个谓词记录 `source_quote`（任务原文片段），来源可审计；
- 逐谓词报告 `docs_matched` 与 `status`（satisfied / unsatisfied）；
- 条件不满足的文档一律排除并给出逐文档理由；
- **全部谓词不可满足时，结果集为空并输出冲突诊断，绝不放宽**。

支持的谓词字段：`year`（年份/区间/近 N 年）、`project_id`（项目/课题/基金编号）、
`doc_type`（PDF/Word/Excel/PPT/扫描件）、`version`（最新版/终版/vN/旧版，
与 lineage 协作）、`batch`（批次号）、`path_scope`（目录范围）、
`permission`（仅可读，默认硬约束）。

## 2. 运行契约（先读再动）

| 项 | 约定 |
|---|---|
| 案例输入 | `/input/case.json`（`case_id`、`output_contract`）与 `/input/task.md` |
| 工作目录 | `/app/work`；最终输出 `/app/output` |
| 预算 | 64 次模型请求 / 900 秒——条件编译与执行全脚本化 |

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
# 步骤3.5 【旗舰】约束编译 + 硬过滤执行
python3 $SKILL/scripts/constraints.py --work-dir $W --task-file /input/task.md
#   → predicates.json / filter_audit.json / filter.json
python3 $SKILL/scripts/retrieve.py --work-dir $W --query "<核心问题>" \
    --filter "$(cat $W/filter.json)" --topk 10
python3 $SKILL/scripts/verify.py --work-dir $W
python3 $SKILL/scripts/report.py --skeleton --input-root /input --work-dir $W --output-dir $O
# 补 answer（必须回应每个谓词的满足情况）后 finalize
python3 $SKILL/scripts/report.py --finalize --input-root /input --work-dir $W --output-dir $O
```

## 5. 硬过滤纪律（必须遵守）

1. `filter_audit.json` 是决策真相：每个文档 kept/excluded 及理由；answer 中不得出现
   被排除文档的证据。
2. 谓词 `unsatisfied` 时：若其余谓词可满足 → 在答案中**显式报告该条件无匹配**并给出
   诊断（是年份无覆盖、编号不存在，还是类型冲突）；若全部不可满足 → 结果为空，
   status=`partial` 或 `failed`，`empty_reason` 写明冲突详情。
3. **禁止**为了"给出答案"而删除或弱化谓词；需要放宽时只能由任务原文明确指示。
4. 条件解析置信度低（`confidence < 0.8`）的谓词，在 answer 中标注"按…理解"。
5. 默认硬约束：不可读文件一律排除（不解密、不越权），记录 `no_permission`。

## 6. 异常处置决策表

| 情况 | 处置 |
|---|---|
| 任务无任何显式条件 | 仅执行默认 permission 谓词，answer 说明"未施加额外条件" |
| 条件互相冲突（如"只要扫描件"且"只要 Excel"） | 两谓词都保留，冲突在 audit 中可见；结果为空并诊断 |
| 年份仅见于正文而非文件名 | 用正文前部年份元数据判定，仍写入谓词依据 |
| project_id 在多个文件出现 | 全部保留，按检索打分排序 |
| 无 output_contract | 默认字段集 + uncertainty 说明 |

## 7. result.json 组装规则

- `--skeleton` 预填：files、evidence（verified）、failures、filters（谓词+逐文档审计）。
- answer 撰写要求：先一句话给出"在条件 X、Y、Z 下命中 N 处"；再列证据；对每个
  unsatisfied 谓词单独说明；禁止出现审计外文件。
- status：有 unsatisfied 谓词但有部分结果 → `partial`；全空 → `partial`/`failed`（视
  empty_reason）；完美满足 → `success`。
- `--finalize` 校验契约完备、manifest 哈希、changes 变更记录。

## 8. 最小调用示例（示意输出，非正式案例结果）

```bash
# task.md: "2020到2022年之间、项目XT-2021的Word实验记录里，缓冲液批次B7的配方是什么？"
python3 $SKILL/scripts/constraints.py --work-dir /app/work --task-file /input/task.md
# → predicates: year between[2020,2022] (src "2020到2022年之间")
#               project_id contains XT-2021 (src "项目XT-2021")
#               doc_type in [docx,doc-legacy] (src "Word")
#               batch contains B7 (src "批次B7"); 全部 satisfied
python3 $SKILL/scripts/retrieve.py --work-dir /app/work --query "缓冲液 配方" \
    --filter "$(cat /app/work/filter.json)"
# → 命中全部来自满足条件的文件；evidence 附 filter_audit 支撑
```

## 9. 不适用情况

联网查新、综述写作、权限系统建设；需要"语义上近似满足"的模糊条件（如"较新的版本"）
——本引擎按显式标签/日期判定，语义近似由模型在 answer 中另行说明并标注不确定性。
