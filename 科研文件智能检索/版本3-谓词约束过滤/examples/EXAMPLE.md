# 最小调用示例（合成演示，非正式案例结果）

**输入（合成）**：`/input/task.md` 任务文本：
"2020 到 2022 年之间、项目 XT-2021 的 Word 实验记录里，缓冲液批次 B7 的配方是什么？"

**调用**：

```bash
python3 $SKILL/scripts/constraints.py --work-dir /app/work --task-file /input/task.md
python3 $SKILL/scripts/retrieve.py --work-dir /app/work --query "缓冲液 配方" \
    --filter "$(cat /app/work/filter.json)"
```

**示意输出（节选，标注为示例）**：

```json
// predicates.json
[
  {"field": "year",       "op": "between", "value": [2020, 2022],
   "source_quote": "2020 到 2022 年之间", "docs_matched": 3, "status": "satisfied"},
  {"field": "project_id", "op": "contains", "value": "XT-2021",
   "source_quote": "项目 XT-2021", "docs_matched": 2, "status": "satisfied"},
  {"field": "doc_type",   "op": "in", "value": ["docx", "doc-legacy"],
   "source_quote": "Word", "docs_matched": 4, "status": "satisfied"},
  {"field": "batch",      "op": "contains", "value": "B7",
   "source_quote": "批次 B7", "docs_matched": 2, "status": "satisfied"},
  {"field": "permission", "op": "readable", "value": true,
   "source_quote": "默认硬约束:仅可读文件", "docs_matched": 9, "status": "satisfied"}
]
```

最终 answer 只引用同时满足全部谓词的 1 个 Word 文件；`filter_audit.json`
给出每个被排除文件的具体理由（年份越界/编号不符/类型不符…）。此演示数据为
合成生成，仅说明接口与流程。
