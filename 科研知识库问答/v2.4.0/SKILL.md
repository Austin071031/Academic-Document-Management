---
name: kbqa-v2-efficiency-budget
description: 科研知识库问答与资料治理流水线(v2 预算治理与证据打包版)。当任务涉及对本地科研资料库(论文 PDF、Office 文档、文本、含重复副本与历史版本)进行盘点、整理、检索、带来源引用的问答、证据回链(文件/版本/页码/段落坐标)、版本与去重管理、元数据维护、不确定性分级,或输入中出现 /input/case.json、output_contract、文档库/知识库问答等约定时使用。Use when a case asks to inventory, organize, search or answer questions over a local research document library with citations traceable to file, version, page and paragraph.
---

# 科研知识库问答 v2:预算治理与证据打包(效率增益方向)

## v2.4.0 相对 v1.0.0 的变更(只改一件事)

评分细则"使用增益 25 分"评"是否减少检索轮次、人工核对条目或定位步骤"以及"增益可验证性"。v1 的逐题多次检索 + 逐文件阅读在 64 请求/900 秒预算下容易被迫中途收尾。v2.4.0 增加 `scripts/kb_pack.py` 并给出**硬性预算纪律**:

- **证据打包**:全部问题的 top 命中去重后合并为单个 `evidence_pack.txt`(每题 ≤6000 字符,坐标头齐全),**Agent 一次 read 完成全部命中段落过目**——模型阅读轮次从"每题多次"降为 1 次;
- **请求预算表**:全流程模型调用封顶 8 次(见下表),其余全部 bash;留 56 次余量应对意外;
- **增量保盘**:每个关键节点后立即更新 result.json,任何时刻中断都有可评分的交付物;
- **可验证性**:`pack_report.json` 记录每题打包命中数与总字符,`ops_log.jsonl` 记录阶段命令,效率增益有据可查。

**其余 v1 行为(引用纪律、缺证、版本规则、异常处置)全部不变。**

## 工作流与请求预算

| 步骤 | 命令/动作 | 模型请求 |
|---|---|---|
| 0 | `cat /input/case.json`;立即写 result.json 骨架(contract 字段全 null,status=partial) | 1 |
| 1-5 | 五条脚本命令(inventory→extract→versions→index→search --questions),期间读 3 个 *_summary.txt | 2 |
| 5b | `python3 /skills/weekly-skill/scripts/kb_pack.py --work /app/work` | 0 |
| 6 | **一次 read** `evidence_pack.txt`;逐题核对撰写 answers.json | 2 |
| 6b | 无命中题换词重查(仅必要时)+ 重跑 search/pack | ≤2 |
| 7 | `kb_result.py` 合成;读 report.md 自查 | 1 |
| 合计 | | ≤8 |

## 增量保盘点

1. 步骤 0 后:result.json 骨架已存在;
2. 步骤 5 后:把 answers.json 骨架(问题清单+状态 partial)写入并立即跑一次 kb_result.py;
3. 每答完一题:重写 answers.json 并跑一次 kb_result.py(秒级,幂等);
4. 预算告警(剩余 <10 请求或 <120 秒):停止补查,把已答内容合成,status=partial 结束。

## 检索效率纪律

- 问题清单**一次批量**投入 `kb_search.py --questions`,不逐题串行检索;
- 单题命中不足时才追加同义词重查,且追加后重跑 pack;
- 回原文复核只在"摘录需扩展上下文"时进行,用 `path/页码/段落号` 直接定位 `text/<file_id>.txt`,不做全文重读。

## 资源清单

- `scripts/kb_inventory.py / kb_extract.py / kb_versions.py / kb_index.py / kb_search.py / kb_result.py`(与 v1 相同)
- `scripts/kb_pack.py`(本方向新增:证据打包与预算报告)
- `references/citation-and-evidence.md / output-contract.md / edge-cases.md`、`examples/minimal-example.md`

全部脚本仅依赖 Python 3 标准库;PDF 抽取用环境 `pdftotext`;异常处置矩阵与 v1 一致(见 references/edge-cases.md)。
