---
name: research-library-cas-lineage-v2-1
description: 把乱糟糟的科研资料库整理成内容寻址对象库（sha256 去重）+ 规范目录工作树 + 版本谱系 DAG，并渲染真实 SVG/PNG 证据图、支持按 sha256/文件名恢复与索引重建、提交契约自检，最终产出诚实的 result.json。
---

# 科研资料库与文件管理 · v2.1.0（内容寻址对象库 + 版本谱系图谱 + 可核验证据强化）

## ① 触发与适用条件

当任务满足以下任一特征时使用本 Skill：

- 输入是 `/input` 下一个**混乱的科研资料库**：中文/特殊字符文件名、改名备份副本（别名）、管理性版本备注（CSV/md）、伴随元数据表、zip/tar 压缩包、深层目录、可能无权限读的文件、内容相同名字不同的重复文件、同一文档的多个历史版本；
- `/input/case.json` 含 `case_id`、`output_contract`（必须全部填充的字段），可能含 `searches` / `questions` / `recovery`（恢复请求）；
- 需要回答：文件清单与归类、重复/别名识别、版本新旧与差异、关键词检索定位、目录结构重建。

不适用边界见 ⑤。

## ② 执行协议（严格按序，确定性工作全部交给脚本）

```bash
python3 /skills/weekly-skill/scripts/cas_run.py --input /input --work /app/work --output /app/output
```

一条命令跑完以下全链路；任何单步失败都会被记账并继续，不崩溃：

- **step0 检查输入**：确认 `/input` 存在、有无 `case.json`。
- **step1 cas_ingest**：每个文件流式 sha256（1 MiB 分块）→ 存入
  `/app/output/library/objects/<sha前2位>/<sha256>`（硬链接优先、复制兜底、对象只存一份、置只读）；zip/tar 用 stdlib 安全展开（防目录穿越、cp437→UTF-8 文件名还原、嵌套限深 2 层）并把成员逐个入库；空目录、符号链接、坏包、不可读文件全部登记进账本 `objects.jsonl`。
- **step1b 保底**：ingest 完成后**立即**写一次 `status="partial"` 的 `/app/output/result.json`，后续步骤失败也有产出。
- **step2 build_index**：解析文件名模式 `项目号_作者_年份_类型.ext`（字段带 provenance，抽不到为 null+原因，绝不猜）；伴随 CSV / 管理备注 md 按文件名 join 为 notes；checkout 出 `library/tree/`（按 `项目/年份/类型/规范文件名` 组织；**复制而非硬链接**以保护对象库；重名冲突追加 `__dupN`，绝不覆盖）→ `library/index.json`。
- **step3 lineage**：sha256 分组得**精确重复组**（别名/副本，按内容不按文件名）；文本文件两两 difflib 行级相似度 ≥0.40 并查集聚类成**版本簇**；簇内按 mtime 排序建链，相邻版本生成 `supersedes` 边（含 similarity、diff_summary 行增删数）→ `versions.json` + `versions.dot`（Graphviz）。
- **step4 search**：对 tree/ 文本建倒排索引（拉丁词 + CJK 单字/二元组 → [(path, 行号)]），回答 case.json 的 searches/questions，每条命中带 文件+行号+片段 → `search_results.json`。
- **step5 finalize + verify**：合并生成最终 `result.json`（case_id + output_contract **全部字段** + status + sources + evidence + uncertainty + change_records）；`verify_cas.py` 重新哈希 tree/ 与对象库逐项比对，报告 `verify_report.json`。
- **step6 render evidence**（v2.1.0 新增）：`render_evidence.py` 纯标准库手写 SVG 把版本谱系 DAG 渲染为**真实可目视检查的证据图** `library/evidence/lineage.svg`（节点=sha256、红箭头=supersedes 含 similarity/行增删、紫区=精确重复组）+ `tree_overview.svg` 目录树概览；若环境有 matplotlib 再渲染 `lineage.png` 预览（optional 导入，**缺失时登记 "matplotlib unavailable, SVG only" 进 uncertainty 与 result.json，绝不报错崩溃**）。
- **step7 recover/qa**（v2.1.0 新增）：`recover.py` 按 case.json 的 recovery 请求从对象库 `objects/` 按 **sha256 前缀或文件名**恢复任意文件到 `library/tree/recovered/` 并**重新哈希校验**（写 `recovery_log.jsonl`，冲突 `__dupN` 不覆盖），随后重建 `index.json` 与检索索引；若 case.json 含 searches/questions 则重跑基座 search.py 并把带 文件+行号+片段 证据的结果同步写 `/app/output/search_results.json`；恢复后自动重跑 verify 保持核对一致。最后 `preflight_check.py` 做提交契约自检（frontmatter 合法且 description ≤900B、≤50 文件、单文件 ≤500KB、总 ≤2MB、全 UTF-8、无符号链接）→ `preflight_report.json`。

跑完后代理只需：读 `result.json` 与各产物，把 evidence/uncertainty 如实转述进最终答复；不要手工重算任何哈希或相似度。

## ③ 输出清单（/app/output）

| 路径 | 内容 |
|---|---|
| `result.json` | 最终结果：case_id + 契约全字段 + status/sources/evidence/uncertainty/change_records |
| `library/objects/<前2位>/<sha256>` | 内容寻址对象库（唯一真相源，只读） |
| `library/objects.jsonl` | 对象账本：路径、sha256、size、mtime、权限、origin、readable/skipped+原因 |
| `library/index.json` | 逻辑索引：逻辑路径→content_id→源路径/mtime/权限/来源 + 带 provenance 的元数据 + notes |
| `library/tree/` | 规范工作树 `项目/年份/类型/规范文件名`（冲突 `__dupN`） |
| `library/versions.json` / `.dot` | 版本谱系 DAG：nodes/edges(supersedes, similarity, diff_summary)/duplicate_groups |
| `library/search_results.json` | 检索命中：文件+行号+片段 |
| `library/verify_report.json` | 复跑核对报告（第三方可独立重跑 verify_cas.py） |
| `library/evidence/lineage.svg` (+`.png` 尽力) / `tree_overview.svg` | 版本谱系/目录树**真实渲染证据图**（SVG 纯标准库必出） |
| `library/recovery_log.jsonl` | 恢复流水：sha256/文件名解析、目标、hash_verified |
| `search_results.json`（顶层） | 检索结果同步副本，便于评审查阅 |
| `preflight_report.json` | 提交契约自检报告（≤50 文件/≤500KB/≤2MB/UTF-8/无符号链接） |

## ④ 异常处理对照表

| 异常 | 行为 | 记账位置 |
|---|---|---|
| 无权限/不可读文件 | 捕获 PermissionError/OSError，readable=false + 原因，计"跳过"继续 | objects.jsonl、index.skipped、result.uncertainty |
| 坏 zip/tar | 记 broken + 原因，原包字节仍入库，不展开 | objects.jsonl、index.broken_archives、result.uncertainty |
| 压缩包目录穿越/cp437 乱码名 | 成员名安全化（去 `..`/绝对路径）、cp437→UTF-8 还原 | ingest 内部 |
| 符号链接 | 不跟随，登记 skipped | objects.jsonl |
| 空目录 | 登记 type=dir empty=true | objects.jsonl、index.empty_dirs |
| tree 重名冲突 | 追加 `__dupN`，绝不覆盖 | index.stats.tree_conflicts_renamed |
| 契约字段无法映射 | 置 null + uncertainty 说明，**绝不编造** | result.uncertainty |
| 单步骤抛异常 | 记账并继续后续步骤；result.json 至少为 partial | work/run_log.json |

## ⑤ 不适用边界

- 输入不是文件资料库整理（如纯问答、纯计算）；
- 需要理解 PDF/Word/图片等二进制内容语义（本 Skill 只做字节级哈希与文本嗅探，不解析二进制文档内部）；
- 需要跨大文件做秒级模糊匹配的大规模语料（difflib 两两比较为 O(n²)，仅适配评测规模，内部已用 quick_ratio 剪枝）；
- 需要修改原始资料库内容的任务（本 Skill 对 /input 只读，所有产物写入 /app/output）。
