---
name: kbqa-v2-evidence-verify
description: 科研知识库问答与资料治理流水线(v2 证据机器核验版)。当任务涉及对本地科研资料库(论文 PDF、Office 文档、文本、含重复副本与历史版本)进行盘点、整理、检索、带来源引用的问答、证据回链(文件/版本/页码/段落坐标)、版本与去重管理、元数据维护、不确定性分级,或输入中出现 /input/case.json、output_contract、文档库/知识库问答等约定时使用。Use when a case asks to inventory, organize, search or answer questions over a local research document library with citations traceable to file, version, page and paragraph.
---

# 科研知识库问答 v2:证据逐条机器核验(正确性与可核验性方向)

## v2.1.0 相对 v1.0.0 的变更(只改一件事)

v1 要求引用"必须真实",但核验靠 Agent 自觉;一旦 exact_quote 记错一两个字、页码抄错,整题正确性就丢分。v2.1.0 增加 `scripts/kb_verify.py`,**把引用真实性从纪律变成机器检查**:

- 每条 evidence 的 `exact_quote` 必须与抽取文本逐字一致(空白归一比对);**轻微空白/换行差异自动修齐为原文精确子串**并回填 `char_start/char_end`;
- `page`(按 \f 分页)与 `para_index`(按锚点命中)**自动重算回填**,不再依赖手抄;
- `path` 必须在 inventory 中,自动附 `sha256_16` 指纹;
- 核验失败的证据标记 `verified=false` —— **携带 verified=false 的证据不得提交**,必须删除或替换。

**其余 v1 行为(引用纪律、缺证、版本规则、异常处置)全部不变。**

## 工作流(相对 v1 只多一步核验)

```bash
# 阶段 0-5 与 v1 完全一致
python3 /skills/weekly-skill/scripts/kb_inventory.py --roots <LIB> --work /app/work
python3 /skills/weekly-skill/scripts/kb_extract.py --inventory /app/work/inventory.json --root <LIB> --work /app/work
python3 /skills/weekly-skill/scripts/kb_versions.py --inventory /app/work/inventory.json --work /app/work [--rules /app/work/version_rules.json]
python3 /skills/weekly-skill/scripts/kb_index.py --work /app/work
python3 /skills/weekly-skill/scripts/kb_search.py --work /app/work --questions /app/work/questions.json --topk 8

# 阶段 6 撰写 answers.json(规范见 references/citation-and-evidence.md)
#   注意: 阶段 6 只需要写 path + exact_quote 大意即可, 坐标由核验自动修齐,
#   但仍须回到原文确认摘录确实支持论断。

# 阶段 6.5(新增,必做): 机器核验
python3 /skills/weekly-skill/scripts/kb_verify.py --work /app/work
# 输出 answers_verified.json + verify_report.json; 有 verified=false 必须先处理
cp /app/work/answers_verified.json /app/work/answers.json   # 全部通过后采用核验版

# 阶段 7 合成交付(与 v1 相同)
python3 /skills/weekly-skill/scripts/kb_result.py --case /input/case.json \
  --answers /app/work/answers.json --work /app/work --outdir /app/output
```

## 引用格式(v1 规范不变,此处重申)

- 每题 `answer` 中论断挂 `[E#]`,与 `evidence` 列表一一对应;
- 证据五要素: `path / version_label / page / para_index / exact_quote`(60–200 字逐字摘录);
- `questions_without_evidence` 写清检索范围与缺失;`conflicts` 并列双方坐标与取信依据;
- 不确定性 A(单一可靠源)/B(多源一致)/C(冲突)/D(OCR 或覆盖不全),每题必标。

## 为什么这能提分

评分细则"结果正确性 15 分"评"引用是否真实、定位是否准确、答案与证据是否逐句对应";"结果可核验性 5 分"评"引用定位能否支撑独立复核"。`verify_report.json` 本身即复核证据:逐条记录 verified/fixed/自动回填的坐标,随包交付。

## 资源清单

- `scripts/kb_inventory.py / kb_extract.py / kb_versions.py / kb_index.py / kb_search.py / kb_result.py`(与 v1 相同)
- `scripts/kb_verify.py`(本方向新增:证据机器核验与坐标修齐)
- `references/citation-and-evidence.md / output-contract.md / edge-cases.md`、`examples/minimal-example.md`(合成数据示例)

全部脚本仅依赖 Python 3 标准库;PDF 抽取用环境 `pdftotext`;扫描件走 OCR 回退并降级为 D 级(见 references/edge-cases.md)。
