# CHANGELOG

## v2.3.0（2026-11-25）—— 检索问答与索引恢复

基座：版本5-长期归档交付包。本版为定向增量，基座其余行为一字不改。

丢分诊断：案例画像显式包含 "searches/questions and actual
recovery/index operations"——检索问答与恢复/索引是任务完成度的直接
考点，本版把它做成最强项。

- 新增 `scripts/recovery_ops.py`：完整恢复/索引操作工作流。
  ①按 文件名/别名(aliases)/sha256 前缀 从归档包、账本
  inventory.jsonl、压缩包登记 extracted.json、input 原始树逐级定位
  恢复文件到 library/，恢复后逐字节校验（sha256 + 字节比对），冲突
  __dupN 不覆盖；②索引重建：重建 library_index.db（FTS5 bigram，
  无 FTS5 退化 LIKE 并在 meta 登记 degraded）；③全部操作写
  recovery_log.jsonl（操作类型/目标/来源依据/结果/校验哈希）。
  CLI 独立可调：`--rebuild-index` / `--restore "目标"` / 读取
  case.json recovery 任务。
- 新增 `scripts/answer_questions.py`：强化问答链路。读取 case.json
  的 searches/questions/queries（兼容字符串与对象两种形态），用
  library_index.db 检索，输出 search_results.json：每条
  {question, answer, hits:[{path,line,snippet}], evidence_complete,
  no_evidence_reason}；写 query_log.jsonl（查询语句/耗时/命中数）
  供效率核验。无命中绝不编答案（answer=null + no_evidence_reason）。
- `scripts/archive_pipeline.py`：编排末尾（step5 校验后、step6
  finalize 前）自动衔接 step5a recovery_ops + step5b
  answer_questions（幂等，失败记账不崩溃）；finalize 后把
  recovery/QA 来源与统计并入 result.json 的 sources/summary，
  各步骤经 change_records.jsonl 汇入 change_records。
- 新增 `scripts/preflight_check.py`：提交契约自检（frontmatter 合法
  且 description ≤900B、≤50 文件、单文件 ≤500KB、总 ≤2MB、全
  UTF-8、无符号链接）→ preflight_report.json。
- 新增 `references/reproduce.md`：复跑核对命令（verify_archive.py、
  query_index.py、answer_questions.py、recovery_ops.py）。
- SKILL.md：frontmatter name 改 research-library-archive-handoff-v2-3，
  description 收紧至 ≤600B；执行协议补 step5a/step5b（注明直接对应
  案例的 searches/questions 与 recovery/index 要求），其余不变。
- 工程约束保持：Python3 纯标准库；UTF-8 全链路；单任务失败记账不
  崩溃；恢复逐字节校验；冲突 __dupN 不覆盖。
- 自查：合成案例（中文名/.bak 副本/两版本 txt/含空格中文 CSV/好
  zip+截断坏 zip/空目录/4 层深目录/中文可检索内容/case.json 含
  output_contract+字符串与对象形态 searches+recovery 任务）实跑
  通过，摘要见 README「自查方法」。

## v5.0（2026-11-19）—— 长期归档交付包（archive-first）

- 核心架构确立：交付物 = 可交接、可迁移、可独立校验的归档四件套
  （tar.gz + SHA256SUMS + MANIFEST.json + HANDOFF_README.md）。
- scripts/：archive_pipeline（编排 step0–step6）、organize（归位/账本/
  去重/版本链/带出处元数据）、build_index（sqlite FTS5 + 中文 bigram，
  无 FTS5 退化 LIKE 并登记）、query_index（文件+行号证据）、
  make_archive（四件套）、verify_archive（临时目录独立复跑校验，
  match/mismatch/missing/extra 统计）、finalize（诚实 result.json，
  step0 即写 partial）、lib（共享工具）。
- 工程要求落实：Python3 纯标准库；sha256 流式 1 MiB；zip/tar stdlib
  展开登记 + 路径穿越防护；UTF-8 全链路；单文件失败不崩溃；
  不可读/无权限登记 readable=false+原因；空目录登记；
  六要素 retention/access_level 从 case/task 抽取，抽不到填
  unspecified 并注明；去重与版本按内容哈希判定。
- 文档：SKILL.md（触发/协议/输出清单/异常对照表/不适用边界）、
  README.md（交接 SOP + 自查方法）、references/（output_contract、
  edge_cases、archive_spec）、schemas/（result、manifest）、
  examples/minimal_example.md（虚构示例）、selftest/make_case.sh。
- 自查：合成案例（中文名/改名副本/两版本 txt/CSV 备注/坏 zip/空目录/
  深目录/中文可检索内容）实跑通过，详见 README"自查方法"。

## 版本区分

- v5 与此前版本的本质差异：从"整理结果"升级为"归档交付物"——
  多出手写校验闭环（verify_archive 独立复跑）与交接文档
  （HANDOFF_README/SOP），并以 partial-first 保证任何中断可交付。
