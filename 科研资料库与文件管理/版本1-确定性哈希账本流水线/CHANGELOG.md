# CHANGELOG

## v1.0.0（2026-11-19）

- 初始版本：确定性哈希账本流水线。
- `scripts/library_pipeline.py`：scan / plan / apply / report / verify 子命令 + 全链路默认入口；1 MiB 分块流式 sha256；append-only 账本 inventory.jsonl；zip/tar 安全展开（防路径穿越）登记 archive_member；`项目/年份/数据类型/` 归位树；`__dupN` 冲突消解；内容哈希精确去重（零字节排除）；difflib(0.75)+mtime 版本链与 superseded_by；元数据三级来源（filename/companion_table/admin_note）全带 evidence，缺失 null+原因。
- `write_partial_result.py`：apply 后尽早落盘 partial result.json（逐项 output_contract 占位 + sources/uncertainty/change_records）。
- `finalize_result.py`：合并 Agent 叙述，按 verify verdict 自动修正 status。
- `validate_result.py`：校验 case_id 与 output_contract 全字段，退出码约定。
- references（output_contract / edge_cases / method）、schemas（result / manifest）、examples/minimal_example.md。
- 自查：合成 fixture（中文名、改名副本、双版本 txt、管理备注 CSV、坏 zip、空目录、深目录、好 zip）全链路实跑通过，verify PASS。
