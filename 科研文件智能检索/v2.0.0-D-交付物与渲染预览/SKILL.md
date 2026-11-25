---
name: research-doc-deliverables-preview
description: 科研文件智能检索 v2.0.0-D——交付物生成与渲染预览。当案例要求交付组织化产物（文件清单 catalog、版本注记、检索报告）或 Office 交付物（Excel/Word/幻灯片）时使用：自动生成结构化交付物、按运行契约为可编辑文件渲染真实 PDF/PNG 预览、沉淀可复用目录规范与元数据 schema。父辈：版本谱系图谱（平台 68.67 分）。不适用开放网络检索与权限建设。
---

# 科研文件智能检索 · 交付物与渲染预览（v2.0.0-D）

**父辈版本**：版本谱系图谱 v1.0.0（attempt 89366，68.6667 分）。
**本迭代唯一主攻**：运行契约要求"Editable Office/slide/diagram outputs should
also have real rendered PDF/PNG previews"——父辈只输出 result.json。`deliver.py`
生成组织化交付物 + 真实 OOXML + 渲染预览 + 可复用模板资源。

## 1. 运行契约（先读再动）

| 项 | 约定 |
|---|---|
| 案例输入 | `/input/case.json`（`case_id`、`output_contract`）与 `/input/task.md` |
| 工作目录 | `/app/work`；最终输出 `/app/output`（result.json + catalog.* + 报告 + 预览） |
| 预算 | 64 次模型请求 / 900 秒 |

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
EXCL=$(python3 -c "import json;print(json.dumps(json.load(open('$W/lineage.json'))['exclude_sha256']))")
python3 $SKILL/scripts/retrieve.py --work-dir $W --query "<核心问题>" --topk 10 \
    --filter "{\"exclude_sha256\": $EXCL}"
python3 $SKILL/scripts/verify.py --work-dir $W
# 步骤3.4 【旗舰】交付物生成（含 Office 写出与渲染预览）
python3 $SKILL/scripts/deliver.py --input-root /input --work-dir $W --output-dir $O
python3 $SKILL/scripts/report.py --skeleton --input-root /input --work-dir $W --output-dir $O
# 补 answer 后 finalize（manifest 自动登记全部交付物哈希）
python3 $SKILL/scripts/report.py --finalize --input-root /input --work-dir $W --output-dir $O
```

## 4. 交付物规范

| 产物 | 内容 |
|---|---|
| catalog.json / .csv / .md | 文件清单 + 元数据（哈希/类别/版本标签/版本角色/提取状态） |
| retrieval_report.md | 检索报告：查询 + 命中表（分数/文件/页/章节/校验/原文片段） |
| versions.md | 版本关系注记（簇、canonical、成员角色与相似度） |
| templates/ | 目录规范模板 + metadata_schema.json（可复用生态资源） |
| catalog.xlsx / 检索结果报告.docx | 仅当任务或 output_contract 要求 Office 交付物时生成 |
| *.pdf / preview-*.png | Office 交付物的真实渲染预览（soffice→PDF→pdftoppm→PNG） |
| deliverables.json | 交付物台账 + 预览状态（preview_unavailable 如实记录） |

## 5. 交付纪律（必须遵守）

1. Office 文件必须是**真实 OOXML**（标准库写出，LibreOffice 可打开）；渲染预览
   必须由渲染管线产出，**绝不伪造预览图**；工具缺失时记 preview_unavailable；
2. 预览失败不影响交付（preview_unavailable 入 deliverables.json 与 failures），
   但 answer 中必须说明；
3. catalog/报告中的数据必须来自 inventory/lineage/verify 产物，逐行可追溯；
4. 任务未要求 Office 交付物时不生成（避免多余产物）；markdown/JSON/CSV 交付物
   总是生成。

## 6. result.json 组装规则

- skeleton 预填；answer 引用 verified 证据与交付物路径；status 依诚实规则；
- finalize 登记全部交付物哈希；Office 交付物在 result.json 中注明其预览文件路径。

## 7. 最小调用示例（示意输出，非正式案例结果）

```bash
python3 $SKILL/scripts/deliver.py --input-root /input --work-dir /app/work --output-dir /app/output
# → deliverables=8 office_previews=1
# → catalog.csv（11 行）、versions.md（1 个修订链）、检索结果报告.docx +
#   检索结果报告.pdf + preview-1.png（真实渲染）
```

## 8. 不适用情况

联网查新、综述写作、权限建设；复杂排版文档（多级样式/图片混排）超出标准库
OOXML 写出能力时，交付 markdown 等价物并说明。
