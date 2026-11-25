---
name: kbqa-v2-auto-pipeline
description: 科研知识库问答与资料治理流水线(v2 一键自动管线版)。当任务涉及对本地科研资料库(论文 PDF、Office 文档、文本、含重复副本与历史版本)进行盘点、整理、检索、带来源引用的问答、证据回链(文件/版本/页码/段落坐标)、版本与去重管理、元数据维护、不确定性分级,或输入中出现 /input/case.json、output_contract、文档库/知识库问答等约定时使用。Use when a case asks to inventory, organize, search or answer questions over a local research document library with citations traceable to file, version, page and paragraph.
---

# 科研知识库问答 v2:一键管线 + 交付自检(可靠性与完成度方向)

## v2.0.0 相对 v1.0.0 的变更(只改一件事)

v1 的 9 个阶段由 Agent 手工串联,容易漏步骤、超时、result.json 缺字段。v2.0.0 把它收敛为**三步**:

```
第一步  python3 /skills/weekly-skill/scripts/kb_run.py --case /input/case.json \
          --work /app/work --outdir /app/output
第二步  阅读 /app/work/answers.json, 逐题核对 _hit_candidates 撰写答案
第三步  python3 /skills/weekly-skill/scripts/kb_result.py --case /input/case.json \
          --answers /app/work/answers.json --work /app/work --outdir /app/output
        python3 /skills/weekly-skill/scripts/kb_selfcheck.py --case /input/case.json \
          --work /app/work --outdir /app/output   # 有问题必须修复后重跑至通过
```

**其余 v1 行为(引用纪律、缺证、版本规则、异常处置)全部不变**,规范文档见 references/。

## 第一步:一键管线 kb_run.py 做了什么

按顺序自动执行并自动写 ops_log.jsonl:

1. **阶段 0**:解析 case.json 的 output_contract,立即写 `/app/output/result.json` 骨架(字段全 null,status=partial)——即使后续中断,交付物也已存在。
2. **盘点→抽取→版本→索引→批量检索**(kb_inventory/kb_extract/kb_versions/kb_index/kb_search,与 v1 相同语义):sha256 哈希、权限、重复组、版本链(管理方 `--rules` 可覆盖)、段落锚点索引、每题 top-8 命中。
3. **预填 answers.json**:每题附 `_hit_candidates`(坐标+摘录候选),Agent 只需核对撰写,不用自己组织检索。
4. 打印 `stage_report.txt`:各阶段耗时与摘要,一次读完即可掌握全局。

可选参数:`--library <路径>` 显式指定资料库根;`--rules version_rules.json` 管理方版本规定;`--all-versions` 版本对比题索引全量。

## 第二步:撰写答案(唯一的模型密集阶段)

- 读 `/app/work/answers.json` 每题的 `_hit_candidates`:坐标页码段落号 + 摘录候选。**必须回到原文核对**(候选只是索引快照),`exact_quote` 取原文逐字连续子串(60–200 字)。
- 每条论断挂 1..n 条证据(path/version/page/para_index/exact_quote/sha256_16),引用编号 `[E1]` 与 evidence 列表一一对应;格式见 `references/citation-and-evidence.md`。
- 无命中或命中不足以回答:answer 写"知识库中没有足够依据回答",把该题移入 `questions_without_evidence` 并写清 `what_is_missing`(检索了哪些词、覆盖哪些文档、为什么不足)。**不许凭常识补答**。
- 版本冲突:并列双方坐标与原文入 `conflicts`,按"管理方规则 > 更新版本 > canonical"取信并写明依据。
- 写完删除 `_hit_candidates` 字段,`status` 改 `complete`(全部完成)或保持 `partial`(有缺证/异常)。

## 第三步:合成 + 自检(kb_selfcheck.py 七项硬检查)

S1 case_id 一致;S2 output_contract 字段全存在(空值须在 missing_contract_fields 声明);S3 每条证据 path 在库内且 exact_quote 是原文逐字子串;S4 `[E#]` 编号与 evidence 列表互洽、不重复;S5 缺证条目含 what_is_missing;S6 冲突条目含 resolution;S7 ops_log 非空且 status 与 missing 字段一致。

**自检不通过必须修复并重跑,直到退出码为 0 再结束任务。**

## 异常与降级(与 v1 相同,详表见 references/edge-cases.md)

- 文件不可读/权限不足:登记 permission 异常;若可能含相关证据,该题 uncertainty 降为 D 并说明。
- 扫描件无文本层(extract 标记 needs_ocr):用环境 OCR 工具处理后写回 `/app/work/text/<file_id>.txt` 再重跑 kb_run.py 的索引/检索阶段(或直接重跑 kb_run.py 全流程,幂等)。
- 资料库为空/缺失:result.json status=failed,说明缺失输入,不编造。
- 预算(64 请求/900 秒)耗尽:kb_run 已保证 result.json 骨架 + 中间产物在场,保持 status=partial 结束。

## 资源清单

- `scripts/kb_run.py` 一键管线(阶段0-5+预填)
- `scripts/kb_inventory.py / kb_extract.py / kb_versions.py / kb_index.py / kb_search.py` 分阶段脚本(与 v1 相同,可单独调用)
- `scripts/kb_result.py` 按 output_contract 合成 result.json + report.md
- `scripts/kb_selfcheck.py` 七项交付自检
- `references/citation-and-evidence.md / output-contract.md / edge-cases.md` 规范
- `examples/minimal-example.md` 合成数据示例(非正式结果)

全部脚本仅依赖 Python 3 标准库;PDF 抽取用环境 `pdftotext`。
