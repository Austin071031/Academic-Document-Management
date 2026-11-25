---
name: research-library-archive-handoff-v2-3
description: 科研资料库归档交付+检索问答+恢复/索引操作：归档四件套可独立校验，searches/questions 证据化作答（无命中不编造），恢复按名/别名/sha256 前缀逐字节校验并重建 FTS5 中文索引。
---

# 科研资料库与文件管理 · v2.3.0 检索问答与索引恢复（archive-first）

## ① 触发与适用

当任务满足以下任一条件时使用本 Skill：

- 输入是"乱糟糟的科研资料库"（中文/特殊字符文件名、改名备份副本、
  管理性 CSV/md 备注、伴随元数据表、压缩包、深层目录、无权限文件、
  重复文件、同一文档多版本），要求整理、检索、交付；
- case.json 含 `output_contract`，要求把结果落到 `/app/output`；
- 评测要求"可交接/可迁移/可独立校验"的交付形态。

不适用边界见 ⑤。

## ② 执行协议

主入口（Agent 只需运行一条命令）：

```
python3 scripts/archive_pipeline.py --input /input --work /app/work --output /app/output
```

协议步骤（脚本内部实现，Agent 不重复实现）：

- **step0 检查**：检查 `/input/case.json`、`task.md` 是否存在、输出目录可写；
  立即写 **partial `result.json`**（即使后续失败也有诚实交付）。
- **step1 organize**：`organize.py` 把资料归位到
  `/app/output/library/<项目>/<年份>/<类型>/`，产出
  `inventory.jsonl`（sha256 账本）、`duplicates.json`（内容哈希去重）、
  `versions.json`（版本链 superseded_by + diff 差异摘要）、
  `manifest.json`/`manifest.csv`（字段带出处 `{field,value,source,evidence}`）。
  六要素：保存期限 retention、密级 access_level 从 case.json/task.md
  正则抽取；抽不到填 `"unspecified"` 并在 uncertainty 注明，绝不编造。
- **step2 build_index**：`build_index.py` 用 stdlib sqlite3 建
  `library/index/library_index.db`（files 表 + FTS5 虚表；中文按字
  二元组 bigram 切词）。无 FTS5 时退化为 LIKE 并在 meta 表登记
  `degraded=true`。
- **step3 query_index**：`query_index.py --db ... --q "关键词"` 回答
  case.json 中 `searches/questions/queries`，命中带 文件+行号 证据，
  汇总写入 `/app/output/search_results.json`。
- **step4 make_archive**：`make_archive.py` 产出 `archive/` 四件套：
  `<case_id>_archive.tar.gz`、`SHA256SUMS`（逐文件哈希清单）、
  `MANIFEST.json`（每文件 路径/大小/sha256/来源/权限/保存期限/密级）、
  `HANDOFF_README.md`（交接说明）。
- **step5 verify_archive**：`verify_archive.py` 解包到临时目录、逐文件
  比对 SHA256SUMS，输出 `verify_report.json`（match/mismatch/missing/
  extra 统计），结论由 finalize 回填 result.json。
- **step5a recovery_ops**（v2.3.0，直接对应案例的 recovery/index
  要求）：`recovery_ops.py` 读取 case.json 的 recovery 任务（字符串或
  对象形态均可），按 文件名/别名/sha256 前缀 从归档包、账本
  inventory.jsonl、压缩包登记、input 原始树逐级定位并恢复文件到
  library/，恢复后逐字节校验；恢复成功即联动重建
  `library_index.db`（FTS5 bigram，无 FTS5 退化 LIKE 并登记
  degraded）。全部操作写 `recovery_log.jsonl`（操作类型/目标/来源
  依据/结果/校验哈希）。CLI 独立可调：
  `python3 scripts/recovery_ops.py --output ... --rebuild-index`
  / `--restore "目标"`。
- **step5b answer_questions**（v2.3.0，直接对应案例的
  searches/questions 要求）：`answer_questions.py` 读取 case.json 的
  searches/questions/queries（兼容字符串与对象两种形态），用
  library_index.db 检索，输出 `search_results.json`：每条
  {question, answer, hits:[{path,line,snippet}], evidence_complete,
  no_evidence_reason}；同时写 `query_log.jsonl`（查询语句/耗时/命中
  数）供效率核验。**无命中绝不编答案**：answer 置 null 并给出
  no_evidence_reason。
- **step6 finalize**：`finalize.py` 写完整 `result.json`：
  case_id + output_contract 逐字段回应 + 诚实 status/sources/
  uncertainty/change_records。

确定性工作（哈希、去重、建库、打包、校验、问题回答）全部在脚本内完成，
模型请求预算留给异常研判，不浪费在可脚本化的步骤上。

## ③ 输出清单

```
/app/output/
├── result.json            # 必需：contract 回应 + status/sources/uncertainty/change_records
├── search_results.json    # 每条检索问题 {answer, hits(path+line+snippet), evidence_complete}
├── query_log.jsonl        # 查询语句/耗时/命中数（效率核验）
├── recovery_log.jsonl     # 恢复/索引操作日志（目标/来源依据/结果/校验哈希）
├── organize_report.json / step0_checks.json / context_snapshot.json
├── inventory.jsonl        # sha256 账本（含跳过与展开登记）
├── duplicates.json / versions.json / extracted.json
├── manifest.json / manifest.csv
├── verify_report.json     # 独立校验报告
├── library/               # 归位后的资料树 <项目>/<年份>/<类型>/
│   └── index/library_index.db
└── archive/               # 归档四件套（核心交付）
    ├── <case_id>_archive.tar.gz
    ├── SHA256SUMS
    ├── MANIFEST.json
    └── HANDOFF_README.md
```

## ④ 异常处理对照表

| 异常 | 处理 |
|---|---|
| 磁盘不足 / 归档创建失败 | 先写 MANIFEST 草稿与 partial result.json；archive_build_error.json 登记原因；status=partial |
| 单个文件不可读 / 无权限 | 登记 `readable=false`+原因，计 skipped，不静默不崩溃 |
| 归档损坏或内容不符 | verify_archive 如实报 mismatch/missing，status≠complete，绝不谎报 ok |
| sqlite 无 FTS5 | 退化为 LIKE 模式，meta 表登记 degraded=true，result uncertainty 注明 |
| 坏压缩包 / 非 stdlib 格式 | extracted.json 登记 failed/unsupported + 原因，原包仍归档 |
| 压缩包路径穿越 | 逐成员 realpath 校验，拦截并登记 blocked |
| retention/access_level 抽不到 | 填 `unspecified`，evidence 注明"未抽到"，写入 uncertainty |
| output_contract 字段未知 | 原样回应并标注 handled=passthrough，不编造值 |

## ⑤ 不适用边界

- 需要联网下载资料、调用外部 API 或写数据库（非 sqlite）的任务；
- 要求对文件内容做语义总结/翻译等强模型判断的任务（本 Skill 只做
  检索命中与结构化管理，不替代阅读）；
- 输入不是文件型资料库（如纯问答 case 无资料文件）时，pipeline
  仍可运行但 archive 内容为空，应在 result.uncertainty 中说明。
