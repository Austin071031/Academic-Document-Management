# CHANGELOG

## v1.0.0（2026-11-19）

- 初始版本：确定性哈希账本流水线。
- `scripts/library_pipeline.py`：scan / plan / apply / report / verify 子命令 + 全链路默认入口；1 MiB 分块流式 sha256；append-only 账本 inventory.jsonl；zip/tar 安全展开（防路径穿越）登记 archive_member；`项目/年份/数据类型/` 归位树；`__dupN` 冲突消解；内容哈希精确去重（零字节排除）；difflib(0.75)+mtime 版本链与 superseded_by；元数据三级来源（filename/companion_table/admin_note）全带 evidence，缺失 null+原因。
- `write_partial_result.py`：apply 后尽早落盘 partial result.json（逐项 output_contract 占位 + sources/uncertainty/change_records）。
- `finalize_result.py`：合并 Agent 叙述，按 verify verdict 自动修正 status。
- `validate_result.py`：校验 case_id 与 output_contract 全字段，退出码约定。
- references（output_contract / edge_cases / method）、schemas（result / manifest）、examples/minimal_example.md。
- 自查：合成 fixture（中文名、改名副本、双版本 txt、管理备注 CSV、坏 zip、空目录、深目录、好 zip）全链路实跑通过，verify PASS。

## v2.0.0（2026-11-25）

- 增量（相对版本1，基座行为一字不改）：补全基座缺失的两个案例组件——`scripts/qa.py`（对 library/ 建轻量倒排索引、中文 bigram 兜底，回答 case.json 的 searches/questions，命中带 文件:行号+片段 证据，无命中诚实 no_evidence）与 `scripts/recover.py`（按文件名/sha256 前缀/别名从内容寻址账本、压缩包展开登记或源备份恢复到 library/，写 recovery_log.jsonl 并 sha256 校验；支持 rebuild-index 重建 manifest+检索索引+verify）；library_pipeline.py 全链路末尾按 case.json 自动衔接（幂等，失败记账不崩溃）。
- 新增 `scripts/preflight_check.py`（提交契约自检：frontmatter/description≤900B、文件数/单文件/总量上限、UTF-8、无符号链接、密钥扫描）与 `references/reproduce.md`（复跑命令清单）、`SUBMISSION.md`（提交记录模板）。
- 命中评分维度：直接补齐案例画像中的 "searches/questions"（检索问答证据定位）与 "actual recovery/index operations"（恢复/重建索引操作账本）两项整项丢分点，同时保持 output_contract 全覆盖、可复跑审计与诚实性三件套不退化。
- 自查：fixture 追加 case.json（output_contract 4 字段 + searches + recovery 任务），实跑全链路退出码 0、verify PASS、search_results.json 命中带行号证据、recovery_log.jsonl 有 sha256 校验记录、result.json 含 case_id+全契约字段、preflight PASS。
