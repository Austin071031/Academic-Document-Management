# CHANGELOG

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
