# output_contract 履约说明

`/input/case.json` 结构（评测方给定，字段名以实际题目为准）：

```json
{
  "case_id": "case-xxx",
  "output_contract": {
    "manifest_path": "…", "duplicates_path": "…",
    "versions_path": "…", "provenance_path": "…", "coverage_report_path": "…"
  },
  "required_fields": ["title", "year"],
  "searches": ["…"], "questions": ["…"]
}
```

## 履约规则（finalize.py 实现）

1. `result.json` 必含：`case_id` + output_contract **全部键** + `status` +
   `sources` + `uncertainty` + `change_records`。
2. output_contract 的每个键：能映射到实际产物（见 `ARTIFACT_MAP`：manifest/library/
   duplicates/versions/provenance/coverage_report 及其 `*_path` 变体）则填
   `/app/output` 下的相对路径；**映射不到填 `null`**，并在 `uncertainty` 追加
   `{"item":"output_contract.<键>","reason":"无对应产物可填，置 null（绝不猜测）"}`。
3. `status`：`complete` = 全部管线步骤退出码 0；否则 `partial`（附 status_reason）。
   不可读输入已登记处理，不算失败。
4. `sources`：`/app/output` 下实际存在的产物清单（manifest.json、manifest.csv、
   duplicates.json、versions.json、provenance.jsonl、field_coverage_report.md、library）。
5. `uncertainty`：不可读文件、PDF 无文本层、坏压缩包、空目录、伴随表未匹配行、
   裁决冲突计数、output_contract 未履约键。
6. `change_records`：来自 `work/change_log.jsonl` 的六要素记录
   （time/action/object/evidence/result/note），覆盖 scan→finalize 全程。
7. **partial 先行**：step0 即写 `status=partial` 的 result.json，防止超时裸奔；
   `--final` 覆盖同一路径。
8. 若 case.json 含 `searches`/`questions`（v2.2.0 起由管线 step2c 自动处理）：
   `qa_cite.py` 对 library/ 建倒排索引作答 → `search_results.json`，答案带
   {file,line,snippet} 引用证据与元数据出处，无证据 no_evidence+缺什么；
   含 `recovery` 时 `recover.py` 自动恢复+校验+索引重建 → `recovery_log.json[l]`。
   契约键 search_results/answers/recovery_log 由 finalize 自动映射产物。
