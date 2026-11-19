---
name: research-doc-evidence-anchor
description: 科研文件智能检索——证据锚点引擎。当任务要求在文件库中定位某段内容并给出可逐字复核的证据（文件、版本、页码、章节、原文片段）时使用。旗舰能力：印刷页↔物理页偏移校正、双栏版式重排、跨页题注续接、逐字回链校验。适用于 PDF/Word/Excel/PPT/文本混合目录；不适用开放网络文献检索与存储权限建设。
---

# 科研文件智能检索 · 证据锚点引擎（版本1）

## 1. 用途与触发

在**已给定的文件库**中回答"某个内容写在哪个文件、哪一版、哪一页、哪一节"，并交付
**可逐字复核**的证据链。本版本旗舰能力是把命中结果落到**段落级锚点**，并处理三个
高频定位错误来源：

1. **印刷页码与 PDF 物理页错位**（正文页脚是印刷页码，物理第 1 页常对应印刷第 N 页）；
2. **双栏排版**（pdftotext 默认按视觉行交错输出，左右栏句子被拆碎）；
3. **跨页表格与图注**（题注被页边界切断，关键词检索漏命中）。

仅在输入文件已存在于本地（`/input`）时使用。不做联网检索，不做权限系统建设。

## 2. 运行契约（先读再动）

| 项 | 约定 |
|---|---|
| 案例输入 | `/input/case.json`（含 `case_id`、`output_contract`、任务参数）与 `/input/task.md` |
| 材料 | `/input` 下的实际文件（PDF 无预提取答案层；以真实文件为准） |
| 工作目录 | `/app/work`（中间产物全部放这里） |
| 最终输出 | `/app/output/result.json`（必须含 `case_id` 与 output_contract 的全部字段）+ 清单、日志、失败记录 |
| 预算 | 64 次模型请求 / 900 秒 / 每次响应 ≤16384 token——**重活交给脚本**，模型只做阅读与汇总 |

**第一步永远是读 `/input/case.json` 与 `/input/task.md`**，确认 `output_contract` 的
字段名与 `case_id`，并在最终 result.json 中原样保留这些字段名（一个都不能少、不能改名）。

## 3. 定位 Skill 资源

```bash
SKILL=/skills/weekly-skill
[ -f "$SKILL/SKILL.md" ] || SKILL=$(dirname "$(find /skills /app/submission -maxdepth 3 -name SKILL.md 2>/dev/null | head -1)")
echo "$SKILL"
```

下文 `$SKILL/scripts/*.py` 均指该目录。脚本只用 Python 3 标准库与系统命令
（pdftotext/pdftoppm/tesseract 按可用性自动降级并如实记录）。

## 4. 标准工作流（按序执行）

```bash
W=/app/work; O=/app/output; mkdir -p "$W" "$O"
# 步骤0 盘点：清单、哈希、权限、重复
python3 $SKILL/scripts/inventory.py --input-root /input --work-dir $W
# 步骤1 提取：PDF按物理页提取，扫描件自动判no_text_layer
python3 $SKILL/scripts/extract.py --input-root /input --work-dir $W
# 步骤1.5 【旗舰】页码校正+版式修复：写回 text_fixed 与 printed_page
python3 $SKILL/scripts/pagefix.py --work-dir $W
# 步骤2 章节切分：标题树、段落锚点（优先采用 pagefix 修正）
python3 $SKILL/scripts/segment.py --work-dir $W
# 步骤3 检索：段落级 BM25，中英分词，缩写双向扩展
python3 $SKILL/scripts/retrieve.py --work-dir $W --query "<从任务抽取的核心问题>" --topk 10
# 步骤4 【旗舰】逐字回链校验：quote存在性、页码一致性、章节存在性
python3 $SKILL/scripts/verify.py --work-dir $W
# 步骤6 组装：镜像 output_contract，先骨架后补全再 finalize
python3 $SKILL/scripts/report.py --skeleton --input-root /input --work-dir $W --output-dir $O
#   ——阅读 $W/hits.json 中 verified=true 的证据，人工（模型）撰写 answer/summary 填入 $O/result.json——
python3 $SKILL/scripts/report.py --finalize --input-root /input --work-dir $W --output-dir $O
```

每个步骤失败仍可继续后续步骤（脚本已做容错），但失败必须进入 `failures`。

## 5. 证据规范（每条结论都必须满足）

每条进入 result.json 的证据必须包含且通过校验：

```json
{
  "file_path": "projectA/XT_report_v2.pdf",
  "sha256": "…",
  "version": "v2",
  "section_path": "2. Methods > 2.1 …",
  "page": 2,              // PDF 物理页
  "printed_page": 22,     // 正文印刷页（pagefix 校正，无依据时为 null）
  "paragraph_id": "d004-p0007",
  "quote": "原文逐字片段（≤220字，能在该文件该页中找到）"
}
```

`verify.py` 会逐条机器校验：quote 逐字存在、页码在范围内、printed_page 与偏移一致、
章节路径在目录中。**未通过校验的证据不得作为结论依据**；若保留，必须标注
`verification_issues` 并降低结论强度。

## 6. 异常处置决策表

| 情况 | 处置 |
|---|---|
| 无权限文件 | inventory 记录 `no_permission`，排除并写入 failures，不尝试绕过 |
| 加密/损坏 PDF | extract 失败原样记录（`extract_failed`），该文件标记 no_text |
| 无文本层扫描件 | 判 `scanned`；有 tesseract 则 OCR 并标注 `ocr_applied`，否则记 `no_text_layer_ocr_unavailable` |
| OCR 结果置信低 | quote 校验可能失败 → 证据标注降级，结论写不确定性 |
| 页码无法建立偏移 | printed_page=null，只报物理页并在 uncertainty 说明 |
| 双栏判定不确定 | pagefix.json 留有 `column_evidence`（分裂位置一致性），重排仅在证据充分时启用 |
| 空结果 | result 必须含 `empty_reason`（是文件没入库、无权限、还是条件未满足），status 不得为 success |
| 无 output_contract | 采用默认字段集：case_id/status/answer/evidence/files/failures/uncertainty，并在 uncertainty 说明 |

## 7. result.json 组装规则

1. `report.py --skeleton` 会按 output_contract 逐字段预填（files/evidence/versions/failures
   来自真实产物；answer/summary/status 留 null 并附 fill_hint）。
2. 模型依据 `verified=true` 的证据撰写 `answer`：`answer` 中每个事实必须能指回 evidence
   数组中的某一条；没有证据支撑的话不要写。
3. `status`：`success`＝全部问题有证据且无障碍记录；`partial`＝有失败/降级/部分回答；
   `failed`＝无法回答。存在 failures 时禁止 success。
4. `--finalize` 会校验契约完备性、清单哈希并写 `manifest.json`（所有输出文件 sha256）
   与 `changes.json`（相对上次运行的变更记录）。
5. Office 类可编辑交付物（docx/xlsx/pptx）若任务要求生成，必须同时渲染 PDF/PNG 预览
   放入 /app/output，并在 manifest 登记。

## 8. 预算纪律

- 步骤0–6 全部脚本化，单次运行总耗时通常 <2 分钟；模型调用只花在：读题（1–2 次）、
  撰写 answer/summary（1–2 次）、复核（1 次）。
- **先落盘再完善**：`--skeleton` 后立即有一份诚实的结果在 /app/output，再改进。
- 重复运行同一案例是安全的（幂等覆盖）；run_journal.jsonl 追加留痕。

## 9. 最小调用示例（示意输出，非正式案例结果）

```bash
# 输入: /input/case.json {case_id:"demo", output_contract:{answer,evidence,files,status}}
#       /input/papers/report_v2.pdf（印刷页码比物理页大10）
python3 $SKILL/scripts/inventory.py --input-root /input --work-dir /app/work
python3 $SKILL/scripts/extract.py --input-root /input --work-dir /app/work
python3 $SKILL/scripts/pagefix.py --work-dir /app/work    # → offset=10, confidence 0.9
python3 $SKILL/scripts/segment.py --work-dir /app/work
python3 $SKILL/scripts/retrieve.py --work-dir /app/work --query "缓冲液配方" --topk 5
python3 $SKILL/scripts/verify.py --work-dir /app/work     # → 5/5 pass
python3 $SKILL/scripts/report.py --skeleton --input-root /input --work-dir /app/work --output-dir /app/output
# 补 answer 后 finalize → result.json 证据: {file_path:"papers/report_v2.pdf", page:2, printed_page:12, quote:"…"}
```

## 10. 不适用情况

开放网络论文检索、论文精读与综述写作、存储系统权限建设、需要外部数据库的查新。
这些超出本 Skill 范围，应直接说明而非硬答。
