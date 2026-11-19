---
name: kbqa-cited-research-knowledge-base
description: 科研知识库问答与资料治理流水线。当任务涉及对本地科研资料库(论文 PDF、Office 文档、文本、含重复副本与历史版本)进行盘点、整理、检索、带来源引用的问答、证据回链(文件/版本/页码/段落坐标)、版本与去重管理、元数据维护、不确定性分级,或输入中出现 /input/case.json、output_contract、文档库/知识库问答等约定时使用。Use when a case asks to inventory, organize, search or answer questions over a local research document library with citations traceable to file, version, page and paragraph, including duplicates, version chains, unreadable files and missing-evidence judgments.
---

# 科研知识库问答:可复核的引用、回链与版本治理

## 这个 Skill 解决什么问题

把"对一份真实科研资料库做检索与问答"做成一条**确定性流水线 + 严格引用纪律**:
每个关键论断必须落到 `文件路径 + 版本 + 页码/段落号 + 原文摘录`;知识库里没有依据的问题必须明确回答"没有"并说明缺什么;所有操作写入日志,他人可按记录复跑。脚本只做机械工作(哈希、抽取、切分、打分),判断与表述由你完成。

## 适用条件与不适用情形

- 适用:案例给出(或指向)一个本地文件资料库,并要求检索、问答、整理、版本/去重/元数据治理、可交接清单中的任意组合。
- 不适用:需要联网检索外部数据库(本流水线只处理本地文件);资料库为空时按第 8 节降级,不编造内容。

## 总原则(每次运行都必须遵守)

1. **只依据真实读到的文件内容作答**;绝不凭文件名、领域常识或标签补造数据。
2. **先存骨架,再增量完善**:读完 case.json 立即写出 result.json 骨架,此后每完成一个阶段就更新一次,避免超时导致空手而归。
3. **缺证就说没有**:检索不到依据的问题,在 `questions_without_evidence` 中登记,说明"检索了哪些文件/版本、为什么不足以回答、还缺什么"。
4. **不把未完成写成完成**:status 只取 `complete / partial / failed`。
5. 每个阶段产生的摘要(inventory_summary / extract_summary / versions_summary)都打印或读一遍,据其决定下一步,不要盲跑。

## 目录与资源

- `scripts/kb_inventory.py` 盘点:哈希、类型、权限、可读性、目录结构
- `scripts/kb_extract.py` 文本抽取(PDF/Office/文本),标记待 OCR 文件
- `scripts/kb_versions.py` 去重、别名、版本链;支持管理方规则 `--rules`
- `scripts/kb_index.py` 段落级锚点索引(默认只索引各文档的 canonical 版本)
- `scripts/kb_search.py` 关键词检索(CJK 二元组 + 拉丁词),单查/批量
- `scripts/kb_result.py` 按 output_contract 合成 result.json 与 report.md
- `references/citation-and-evidence.md` 引用格式、证据条目、不确定性分级模板
- `references/output-contract.md` result.json 合同字段处理规则
- `references/edge-cases.md` 异常矩阵:不可读/无权限/扫描件/空目录/版本冲突/证据矛盾
- `examples/minimal-example.md` 最小调用示例(合成数据,仅示意)

脚本仅依赖 Python 3 标准库;PDF 抽取优先使用运行环境提供的 `pdftotext`。

## 阶段 0:读案例与合同(必须先做)

```bash
cat /input/case.json          # 确认 case_id、资料库路径、任务要求、output_contract
ls -laR /input | head -100    # 确认资料库实际位置与规模
```

- 记录 case_id;找到资料库根目录 `<LIB>`(常在 /input 下,以 case.json 中的字段为准)。
- 找出 case.json 中的 `output_contract`(字段清单或 JSON Schema),这是 result.json 必须完整覆盖的合同。
- **立即**写出 `/app/output/result.json` 骨架:`{"case_id": ..., "status": "partial", ...合同字段全为 null...}`(字段展开规则见 references/output-contract.md)。
- 追加一行操作日志(见第 9 节)。

## 阶段 1:盘点资料库

```bash
mkdir -p /app/work /app/output
python3 /skills/weekly-skill/scripts/kb_inventory.py --roots <LIB> --work /app/work
```

- 读 `inventory_summary.txt`:文件总数、类型分布、不可读文件、符号链接。
- 不可读文件进入异常清单(权限维度);空目录单独登记(目录层级维度)。
- 若 `--roots` 给多个目录,注意重复跨目录副本将在阶段 3 用哈希识别。

## 阶段 2:抽取文本

```bash
python3 /skills/weekly-skill/scripts/kb_extract.py --inventory /app/work/inventory.json --root <LIB> --work /app/work
```

- 读 `extract_summary.txt`。`needs_ocr` 的扫描件:用运行环境的 OCR 工具处理(如 `pdftoppm -r 200 <file> /tmp/pg` 后逐页 OCR),把得到的文本写入 `/app/work/text/<file_id>.txt`,并在 `extract_report.json` 对应条目追加 `"ocr_recovered": true`。OCR 结果引用时必须标注"经 OCR,可能有识别误差"(不确定性降级)。
- 加密/损坏/legacy 二进制文件保留 `error/unreadable` 状态,登记进异常清单,不得静默丢弃。

## 阶段 3:去重与版本链

```bash
python3 /skills/weekly-skill/scripts/kb_versions.py --inventory /app/work/inventory.json --work /app/work
```

- 读 `versions_summary.txt`:多版本文档的 canonical 选择、重复组。
- **若资料库中存在管理性版本说明**(文件名含 version/changelog/README/说明/索引 等,内容规定了哪份为准、谁取代谁):先读该文件,把规定写成 `/app/work/version_rules.json`,重跑:
  `python3 .../kb_versions.py ... --rules /app/work/version_rules.json`
- 版本冲突问题(同一论断在不同版本不一致):按"管理方规则 > 更新版本 > canonical"顺序取信,同时在 `conflicts` 中并列记录两个版本的坐标与原文,不得悄悄丢弃旧版本证据。

## 阶段 4:段落级索引

```bash
python3 /skills/weekly-skill/scripts/kb_index.py --work /app/work        # 默认仅 canonical 版本
# 版本对比类题目再补一份全量索引:
python3 /skills/weekly-skill/scripts/kb_index.py --work /app/work --all-versions
# (第二次运行会覆盖 index.jsonl; 如需同时保留, 先 cp index.jsonl index_canonical.jsonl)
```

锚点坐标 = `path + page + para_index + char_start/char_end`,即"文件、版本、页码、段落"四级回链。

## 阶段 5:检索

```bash
# 单查(快速验证召回):
python3 /skills/weekly-skill/scripts/kb_search.py --work /app/work --query "<问题关键词>" --topk 8
# 批量(案例问题清单):
cat > /app/work/questions.json <<'EOF'
[{"id": "q1", "question": "<问题1>"}, {"id": "q2", "question": "<问题2>"}]
EOF
python3 /skills/weekly-skill/scripts/kb_search.py --work /app/work --questions /app/work/questions.json --topk 8
```

- 对每个问题读 top 命中段落的**全文**(hits 中已含),判断是否真的回答该问题;关键词命中≠语义相关,必须人工(你)过目。
- 命中不足时换关键词同义词重查;仍无依据则走缺证流程(第 6 节)。
- 需要精确出处时,用 `path/页码/段落号` 回到 `text/<file_id>.txt` 或原文件复核。

## 阶段 6:逐题作答与引用

按 `references/citation-and-evidence.md` 的模板撰写 `/app/work/answers.json`:

- 每个答案由若干**论断**组成,每条论断挂 1..n 条**证据**,证据含 `path / version_label / page / para_index / exact_quote`(exact_quote 必须是原文中逐字连续的子串,截取 60–200 字)。
- 引用编号 `[E1] [E2]` 在答案文本中标注,与 evidence 列表一一对应。
- 无依据的问题:answer 写"知识库中没有足够依据回答",`what_is_missing` 说明检索范围与缺失内容。
- 不确定性分级(A 单一来源一致 / B 多来源一致 / C 版本冲突 / D 含 OCR 或不可读文件存疑),每题必标。

## 阶段 7:合成交付

```bash
python3 /skills/weekly-skill/scripts/kb_result.py --case /input/case.json \
  --answers /app/work/answers.json --work /app/work --outdir /app/output
```

- 核对 `/app/output/result.json`:case_id 正确;output_contract 字段**一个不缺**;无依据字段为 null 并列入 `missing_contract_fields`。
- 读一遍 `report.md` 自查:每条论断都能顺着坐标回到原文吗?

## 阶段 8:异常与降级(详见 references/edge-cases.md)

| 情况 | 处置 |
|---|---|
| 文件不可读/权限不足 | 登记 permission 异常;若可能含相关证据,该题不确定性降为 D 并说明 |
| 扫描件无文本层 | OCR 回退;引用标注 OCR 误差风险 |
| 目录为空 / 资料库缺失 | status=failed(或按题目要求),说明缺失输入,不编造 |
| 重复副本 | 哈希组登记,canonical 一份入索引,其余仅登记 |
| 版本冲突 | 并列记录双方坐标与原文,按取信规则选择并说明 |
| 证据互相矛盾 | 不做平均/和稀泥,分别引用并标明冲突 |

## 阶段 9:操作日志与复跑

每执行一条关键命令,向 `/app/work/ops_log.jsonl` 追加一行 JSON:

```json
{"ts": "ISO8601", "step": "inventory|extract|versions|index|search|answer|compose", "command": "...", "status": "ok|skipped|failed", "notes": "..."}
```

`kb_result.py` 会把 `ops_log.jsonl` 复制进 `/app/output`。换人复跑 = 按 case.json + 本文件 + ops_log 重放各阶段命令。

## 预算与降级策略

- 限制 64 次模型请求 / 900 秒:脚本化阶段(1–5)全部走 bash,不要逐文件用模型阅读;模型调用只用于:读案例、读管理性说明、过目命中段落、撰写 answers.json、自查。
- 资料库很大时:阶段 5 只读每题 top-8 段落;仍超时,优先保证 result.json 骨架 + 已答问题的完整性,status=partial。
- 任何时候中断后都可从 `/app/work` 的中间产物恢复,无需重头来过。
