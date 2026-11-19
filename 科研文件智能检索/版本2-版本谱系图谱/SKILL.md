---
name: research-doc-version-lineage
description: 科研文件智能检索——版本谱系图谱。当文件库中存在改名副本、修订版、扫描件、多版本投稿材料，且任务要求"找到正确的那一版、避免把副本当独立证据、说明版本关系"时使用。旗舰能力：哈希级去重 + 内容相似度版本链 + 副本/改名/修订角色判定 + 版本感知检索（副本不作独立证据）。不适用开放网络检索与权限建设。
---

# 科研文件智能检索 · 版本谱系图谱（版本2）

## 1. 用途与触发

科研文件的真实状态是"一团多版本"：同一份报告有 v1/v2/修订版/终版，有改名副本，
有扫描件与原始电子版并存。检索任务最常见的失败是**把副本当成独立证据**（一份内容
数成三份）、**引用旧版当新版**、或**漏掉改名后的文件**。

本版本旗舰能力 `lineage.py` 建立**版本谱系图**：

- `duplicate_exact`：sha256 相同 → 逐字节重复；
- `renamed_copy`：内容相同、文件名规范化后不同 → 改名副本；
- `revision_chain`：内容相似度 ≥0.60 且版本标签/日期可排序 → 修订链，
  推举 canonical（版本阶段最高、标签最新、日期最新）；
- `related_content`：相似度 ≥0.30 → 弱关联（共享段落/数据说明）。

**检索与计数时，每个簇只算一份证据；引用一律指向 canonical 版本，旧版/副本在证据中
以 `version_role` 标注。**

## 2. 运行契约（先读再动）

| 项 | 约定 |
|---|---|
| 案例输入 | `/input/case.json`（`case_id`、`output_contract`、任务参数）与 `/input/task.md` |
| 工作目录 | `/app/work`；最终输出 `/app/output`（result.json + manifest + 日志） |
| 预算 | 64 次模型请求 / 900 秒——重活脚本化，模型只做阅读与汇总 |

第一步读 `/input/case.json` 与 `/input/task.md`，最终 result.json 原样保留
output_contract 全部字段名与 `case_id`。

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
# 步骤2.5 【旗舰】版本谱系：簇、角色、canonical、排除哈希清单
python3 $SKILL/scripts/lineage.py --work-dir $W
# 步骤3 版本感知检索：排除副本/旧版哈希，只保留 canonical 证据
EXCL=$(python3 -c "import json;print(json.dumps(json.load(open('$W/lineage.json'))['exclude_sha256']))")
python3 $SKILL/scripts/retrieve.py --work-dir $W --query "<核心问题>" \
    --filter "{\"exclude_sha256\": $EXCL}" --topk 10
python3 $SKILL/scripts/verify.py --work-dir $W
python3 $SKILL/scripts/report.py --skeleton --input-root /input --work-dir $W --output-dir $O
# 补 answer/summary/status 后：
python3 $SKILL/scripts/report.py --finalize --input-root /input --work-dir $W --output-dir $O
```

`lineage.json` 关键字段：`clusters[].members[].role`（canonical / exact_copy /
renamed_copy / older_revision / intermediate_revision / only_version）、
`exclude_sha256`（副本与旧版哈希，可直接作为硬过滤输入）。

## 5. 版本感知规则（必须遵守）

1. 计数与"多少份证据"类回答，按簇计数，不按键值计数；
2. 引用片段一律带 `version` 与 `version_role`；副本文件即使命中也不单独列为证据，
   在 `versions` 字段说明其归属簇；
3. 任务指定"最新版/终版"时，仅 canonical 参与；指定"旧版/第一版"时反向选择并标注；
4. 版本标签无法判定（无标签、日期冲突）时，`version_role` 写 `only_version` 并在
   uncertainty 说明，**不得猜**；
5. 扫描件与电子版内容相同时，优先引用可逐字校验的电子版，扫描件标注 OCR 来源。

## 6. 元数据字段（清单与证据中维护）

| 字段 | 来源 |
|---|---|
| sha256 | inventory 实测 |
| version_tags | 文件名解析（v2/rev3/第2版/2023-05 等） |
| version_role / cluster_id / is_canonical | lineage 判定 |
| date | 文件名日期优先，缺失用 mtime 并标注来源 |
| project / scope | 路径首段目录名（如 projectA/），仅作线索不作结论 |

## 7. 异常处置决策表

| 情况 | 处置 |
|---|---|
| 无权限/加密/损坏 | 记录 failures 并排除，不绕过 |
| 无文本层扫描件 | extract 判 scanned，OCR 可用则标注 ocr_applied |
| 版本链断裂（中间版缺失） | 链如实呈现缺口，canonical 取现存最高版本并说明 |
| 同名不同内容（误覆盖） | 哈希不同 → 不合并，标 related_content，两个都保留为候选 |
| 全部文档互为副本 | 证据计数=1，在 answer 明确说明 |
| 空结果 | 写 `empty_reason`，status 不为 success |
| 无 output_contract | 默认字段集 + uncertainty 说明 |

## 8. result.json 组装规则

- `--skeleton` 预填：files（清单）、versions（clusters）、evidence（verified 命中）、
  failures、filters（含 exclude 决策审计）。
- answer 撰写要求：涉及版本比较、计数、沿革的结论必须指回 evidence 与 versions；
  无法确定版本关系的表述必须带不确定性说明。
- status 规则：failures 非空或有降级证据 → `partial`；完全无法回答 → `failed`。
- `--finalize` 校验契约字段、写 manifest.json（输出哈希）与 changes.json。

## 9. 最小调用示例（示意输出，非正式案例结果）

```bash
# 输入: /input/proj/{report_v1.pdf, report_v2.pdf, old_copy_report.pdf(=v1内容)}
python3 $SKILL/scripts/lineage.py --work-dir /app/work
# → clusters: [canonical=report_v2, members=[v2/canonical, v1/older_revision,
#              old_copy/renamed_copy]], exclude_sha256=[v1与副本的哈希]
python3 $SKILL/scripts/retrieve.py --work-dir /app/work --query "buffer recipe" \
    --filter '{"exclude_sha256": ["<v1hash>","<copyhash>"]}'
# → 命中只来自 report_v2.pdf；evidence.version_role=canonical
```

## 10. 不适用情况

联网文献查新、论文综述写作、存储权限建设；版本内容语义比对（哪版结论正确）超出
谱系判定范围，需人工/模型在阅读后裁决，Skill 负责把两版的对应段落锚点都交齐。
