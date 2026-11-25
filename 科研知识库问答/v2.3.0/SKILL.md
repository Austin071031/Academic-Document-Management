---
name: kbqa-v2-missing-evidence
description: 科研知识库问答与资料治理流水线(v2 缺证覆盖证明与冲突矩阵版)。当任务涉及对本地科研资料库(论文 PDF、Office 文档、文本、含重复副本与历史版本)进行盘点、整理、检索、带来源引用的问答、证据回链(文件/版本/页码/段落坐标)、版本与去重管理、元数据维护、不确定性分级,或输入中出现 /input/case.json、output_contract、文档库/知识库问答等约定时使用。Use when a case asks to inventory, organize, search or answer questions over a local research document library with citations traceable to file, version, page and paragraph.
---

# 科研知识库问答 v2:缺证判据的覆盖证明(缺证判断力方向)

## v2.3.0 相对 v1.0.0 的变更(只改一件事)

题目核心判据之一是:"**对知识库里确实没有依据的问题,成果是否敢说'没有'并说明缺什么**"。v1 只说"缺证就说没有",但"没有"凭什么成立、检索有没有漏,全凭 Agent 一句话。v2.3.0 增加 `scripts/kb_coverage.py`,**把"没有"变成可核验的覆盖证明**:

对每个问题输出 `coverage_proof.json`:

- `searched_queries`:实际用过的检索词(来自批量检索的分词记录);
- `docs_in_scope`:本次覆盖的 canonical 文档清单;
- `anchors_total / candidates_scored / hits_considered`:索引规模、被评分段落数、过目命中数;
- `docs_excluded`:被排除文档及逐条原因(旧版本/重复副本/不可读/无文本层);
- `verdict_hint`:存在不可读或未索引文档时为 `partial_coverage` —— 此时**不允许下"知识库没有"的强结论**,只能答"在可检索范围内没有依据,但 X 文件因 Y 原因未能覆盖"(uncertainty=D)。

**其余 v1 行为全部不变。**

## 工作流(相对 v1 在阶段 5 后多一步)

```bash
python3 /skills/weekly-skill/scripts/kb_inventory.py --roots <LIB> --work /app/work
python3 /skills/weekly-skill/scripts/kb_extract.py --inventory /app/work/inventory.json --root <LIB> --work /app/work
python3 /skills/weekly-skill/scripts/kb_versions.py --inventory /app/work/inventory.json --work /app/work [--rules /app/work/version_rules.json]
python3 /skills/weekly-skill/scripts/kb_index.py --work /app/work
python3 /skills/weekly-skill/scripts/kb_search.py --work /app/work --questions /app/work/questions.json --topk 8
python3 /skills/weekly-skill/scripts/kb_coverage.py --work /app/work    # 5b(新增)
```

## 缺证回答的判定规则(本方向核心)

1. **补查义务**:单查无命中时,至少换一组同义词/上位词重查(如"转化率"→"conversion/产率/yield"),把全部查询词都记入 `searched_queries`,再跑 kb_coverage.py;
2. `verdict_hint = sufficient_coverage` 且无命中:才允许写"知识库中没有足够依据回答该问题",`what_is_missing` 引用 coverage_proof 说明查了哪些文档、缺什么类型的资料;
3. `verdict_hint = partial_coverage`:写"在可检索的 N 份文档中没有依据;以下文件未能覆盖:<路径+原因>,不排除其中含有相关信息",uncertainty 一律 D;
4. 有命中但答不全:按部分缺证处理,在 `what_is_missing` 写明缺口;
5. **禁止**:有任何证据命中时声称"没有依据";未做补查义务就下"没有"的结论。

## 版本冲突的冲突矩阵(配套纪律)

同一问题在不同版本给出不同结论时,`conflicts` 条目必须包含:双方 `path/page/para_index/exact_quote`、变化方向(数值/结论/范围)、`resolution`(管理方规则 > 更新版本 > canonical)与 `resolution_basis`。不做无依据折中,不悄悄丢弃旧版本证据。

## 资源清单

- `scripts/kb_inventory.py / kb_extract.py / kb_versions.py / kb_index.py / kb_search.py / kb_result.py`(与 v1 相同)
- `scripts/kb_coverage.py`(本方向新增:缺证覆盖证明)
- `references/citation-and-evidence.md / output-contract.md / edge-cases.md`、`examples/minimal-example.md`

全部脚本仅依赖 Python 3 标准库;PDF 抽取用环境 `pdftotext`。
