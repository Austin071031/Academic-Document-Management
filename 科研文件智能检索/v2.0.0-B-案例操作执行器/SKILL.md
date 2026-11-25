---
name: research-doc-case-operations
description: 科研文件智能检索 v2.0.0-B——案例操作执行器。当案例不仅要求检索回答，还要求执行库整理操作（重建索引、登记元数据、别名登记、版本注记、恢复失败文件，即题面所称 recovery/index operations）时使用。父辈：版本谱系图谱（平台 68.67 分）；本迭代主攻操作类任务的完成度。不适用开放网络检索与权限建设。
---

# 科研文件智能检索 · 案例操作执行器（v2.0.0-B）

**父辈版本**：版本谱系图谱 v1.0.0（attempt 89366，68.6667 分）。
**本迭代唯一主攻**：题面工作单明确案例含 *aliases、administrative version notes、
metadata、recovery/index operations*——父辈只检索不操作。`operations.py` 把库整理
操作做成确定性执行器，全部留痕。

## 1. 运行契约（先读再动）

| 项 | 约定 |
|---|---|
| 案例输入 | `/input/case.json`（`case_id`、`output_contract`）与 `/input/task.md` |
| 工作目录 | `/app/work`；最终输出 `/app/output`（result.json + organized_library/） |
| 预算 | 64 次模型请求 / 900 秒——操作全脚本化 |
| 安全红线 | **只读 /input，绝不改动输入文件**；整理产物一律写入 /app/output/organized_library/ |

第一步读 case.json/task.md；result.json 原样保留 output_contract 字段与 case_id。

## 2. 定位 Skill 资源

```bash
SKILL=/skills/weekly-skill
[ -f "$SKILL/SKILL.md" ] || SKILL=$(dirname "$(find /skills /app/submission -maxdepth 3 -name SKILL.md 2>/dev/null | head -1)")
```

## 3. 标准工作流

```bash
W=/app/work; O=/app/output; mkdir -p "$W" "$O"
python3 $SKILL/scripts/inventory.py --input-root /input --work-dir $W
python3 $SKILL/scripts/extract.py   --input-root /input --work-dir $W
python3 $SKILL/scripts/segment.py   --work-dir $W
python3 $SKILL/scripts/lineage.py   --work-dir $W
# 步骤3.2 【旗舰】操作执行：索引复核+catalog+别名登记+版本注记+恢复尝试
python3 $SKILL/scripts/operations.py --input-root /input --work-dir $W --output-dir $O
python3 $SKILL/scripts/retrieve.py --work-dir $W --query "<核心问题>" --topk 10
python3 $SKILL/scripts/verify.py --work-dir $W
python3 $SKILL/scripts/report.py --skeleton --input-root /input --work-dir $W --output-dir $O
# 补 answer（引用 organized_library 产物 + 检索证据）后 finalize
python3 $SKILL/scripts/report.py --finalize --input-root /input --work-dir $W --output-dir $O
```

## 4. 操作产物（organized_library/）

| 文件 | 内容 |
|---|---|
| index_report.json | 索引完整性复核（文档/段落数、文本文档无段落清单、一致性结论） |
| catalog.json | 每文件元数据登记：sha256/类别/大小/版本标签/版本角色/簇/提取状态 |
| aliases_registry.json | 改名副本与规范化名映射（含判定依据） |
| versions.json | 簇级版本链注记 + canonical 推举依据 |
| recovery_log.json | 每个无文本/失败文件的恢复尝试与结果（recovered/failed + 残余证据说明） |
| operations_log.json | 全部操作台账 + 安全声明 |

## 5. 操作纪律（必须遵守）

1. **只读输入**：任何"修复/整理"以记录与副本形式落在 organized_library/，
   不移动、不重命名、不删除 /input 中任何文件；
2. 恢复只尝试非侵入手段（OCR、回退工具）；失败的写明 failed 原因与残余证据
   （如"仅有哈希与元数据"）；
3. answer 中凡引用 catalog/版本注记的结论，必须能指回 organized_library 的对应
   记录与行；检索类结论仍须 verify 逐字校验证据；
4. 声明过的操作未执行必须说明；未声明的操作不臆造执行。

## 6. 异常处置决策表

| 情况 | 处置 |
|---|---|
| 案例无操作声明 | 执行默认全集并说明（题面主线即"整理文件，也保留版本关系"） |
| 操作要求实际改动输入 | 拒绝改动 /input，改为在 organized_library 产出等价记录，并在 answer 说明差异 |
| 恢复对象过多 | 按 budget 顺序处理并记录未处理清单 |
| 无 output_contract | 默认字段集 + uncertainty |

## 7. 最小调用示例（示意输出，非正式案例结果）

```bash
python3 $SKILL/scripts/operations.py --input-root /input --work-dir /app/work --output-dir /app/output
# → operations: 5 executed -> organized_library/
# → aliases_registry.json: old_copy_report.pdf → XT_report_v1.pdf (renamed_copy, sha256 equal)
# → recovery_log.json: scanned_note.pdf failed_no_text_layer（残余证据：哈希+元数据）
```

## 8. 不适用情况

联网查新、综述写作、权限建设；需要真正迁移文件系统的操作（平台沙箱内只做
记录型整理）。
