---
name: kbqa-v2-metadata-source
description: 科研知识库问答与资料治理流水线(v2 六维度元数据与来源溯源版)。当任务涉及对本地科研资料库(论文 PDF、Office 文档、文本、含重复副本与历史版本)进行盘点、整理、检索、带来源引用的问答、证据回链(文件/版本/页码/段落坐标)、版本与去重管理、元数据维护、不确定性分级,或输入中出现 /input/case.json、output_contract、文档库/知识库问答等约定时使用。Use when a case asks to inventory, organize, search or answer questions over a local research document library with citations traceable to file, version, page and paragraph.
---

# 科研知识库问答 v2:六维度元数据、来源溯源与版本差异(完整性方向)

## v2.2.0 相对 v1.0.0 的变更(只改一件事)

评分细则"结果完整性 5 分"明确要求覆盖**六个维度:文件类型、元数据字段、目录层级、重复文件、版本差异、权限与来源**。v1 覆盖了其中四项(类型/目录/重复/权限),**元数据字段与来源只有骨架,版本差异没有量化**。v2.2.0 增加 `scripts/kb_metadata.py` 补齐:

- **元数据字段**:对每个 canonical 文档从抽取文本头部启发式提取 title/authors/year/DOI/arXiv,逐字段记录 `value/source/confidence`;**提取不到的字段如实为 null 并标 missing,绝不编造**;BibTeX/RIS 侧车文件自动登记 `metadata_sidecar`;
- **来源**:每个文件记录库内路径、重复副本归属(`duplicate_of`)、版本取代关系(`supersedes`)、mtime;
- **版本差异**:相邻版本抽取文本的行级 diff 统计(+/− 行数、替换块数),"版本差异"从"列出了版本"升级为"量化了差异"。

**其余 v1 行为全部不变。**

## 工作流(相对 v1 只多一步 3b)

```bash
python3 /skills/weekly-skill/scripts/kb_inventory.py --roots <LIB> --work /app/work
python3 /skills/weekly-skill/scripts/kb_extract.py --inventory /app/work/inventory.json --root <LIB> --work /app/work
python3 /skills/weekly-skill/scripts/kb_versions.py --inventory /app/work/inventory.json --work /app/work [--rules /app/work/version_rules.json]
python3 /skills/weekly-skill/scripts/kb_metadata.py --work /app/work        # 3b(新增)
python3 /skills/weekly-skill/scripts/kb_index.py --work /app/work
python3 /skills/weekly-skill/scripts/kb_search.py --work /app/work --questions /app/work/questions.json --topk 8
# 阶段 6 撰写 answers.json; 阶段 7 kb_result.py 合成
```

## 六维度覆盖自查(交付前对照)

| 维度 | 落点 |
|---|---|
| 文件类型 | inventory.json `by_type` 分布 + 逐文件 ext/type |
| 元数据字段 | metadata.json 逐文档 title/authors/year/doi/arxiv(含 confidence/missing) |
| 目录层级 | inventory.json directories(含空目录标注) |
| 重复文件 | versions.json duplicate_groups + duplicate_paths(sha256) |
| 版本差异 | versions.json 版本链 + metadata.json version_diff(diff 统计) |
| 权限与来源 | inventory.json uid/gid/mode/readable;metadata.json source(路径/归属/取代关系/mtime) |

## answers.json 引用本方向的产物

- `sources` 字段:逐题列出依据文档的 metadata 摘要(path/title/year/doi/canonical),让读者一眼看到"依据的是哪份文献的哪个版本";
- 版本冲突题:引用 metadata.json 的 `version_diff` 说明新旧版本变化幅度,为"取新版本"提供量化依据;
- 元数据类问题(如"这篇 DOI 是多少"):直接以 metadata.json 作答,引用 metadata 条目坐标。

## 资源清单

- `scripts/kb_inventory.py / kb_extract.py / kb_versions.py / kb_index.py / kb_search.py / kb_result.py`(与 v1 相同)
- `scripts/kb_metadata.py`(本方向新增:元数据/来源/版本差异)
- `references/citation-and-evidence.md / output-contract.md / edge-cases.md`、`examples/minimal-example.md`

全部脚本仅依赖 Python 3 标准库;PDF 抽取用环境 `pdftotext`;异常处置矩阵与 v1 一致(见 references/edge-cases.md)。
