# 最小示例（示例，非正式案例结果）

> 以下为**虚构**最小输入与对应产物节选，仅用于说明产物结构，不是正式评测结果。

## 虚构输入 /input

```
/input/case.json
/input/task.md
/input/项目X_李四_2022_报告.txt        # 内容: "实验A 结果 3.1\n结论 初步\n"
/input/备份/报告_最终版.txt            # 与上一文件字节完全相同（改名副本）
/input/项目X_李四_2023_报告_v2.txt     # 内容: "实验A 结果 3.2\n补充 复测\n结论 确认\n"
/input/备注.csv                        # 文件名,备注 / 项目X_李四_2023_报告_v2.txt,投稿版
```

`/input/case.json`：

```json
{
  "case_id": "demo-000",
  "output_contract": ["file_count", "duplicate_groups", "version_chains"],
  "searches": ["实验A"]
}
```

## 运行

```bash
python3 scripts/cas_run.py --input /input --work /app/work --output /app/output
```

## 产物节选（虚构数据）

**library/objects.jsonl**（3 个数据文件 → 2 个唯一对象）：

```json
{"path": "项目X_李四_2022_报告.txt", "sha256": "aaaa…01", "object_created": true, …}
{"path": "备份/报告_最终版.txt",     "sha256": "aaaa…01", "object_created": false, …}
{"path": "项目X_李四_2023_报告_v2.txt", "sha256": "bbbb…02", "object_created": true, …}
```

**library/versions.json**：

```json
{
  "duplicate_groups": [
    {"content_id": "aaaa…01", "paths": ["备份/报告_最终版.txt", "项目X_李四_2022_报告.txt"], "count": 2}
  ],
  "edges": [
    {"from": "bbbb…02", "to": "aaaa…01", "relation": "supersedes",
     "inverse": "superseded_by", "similarity": 0.4,
     "diff_summary": {"lines_added": 2, "lines_removed": 1}}
  ]
}
```

**library/search_results.json**：

```json
{"searches": [{"query": "实验A", "hit_count": 2, "hits": [
  {"path": "tree/项目X/2022/笔记文本/项目X_李四_2022_报告.txt", "line": 1,
   "snippet": "实验A 结果 3.1", "match": "exact"},
  {"path": "tree/项目X/2023/笔记文本/项目X_李四_2023_报告_v2.txt", "line": 1,
   "snippet": "实验A 结果 3.2", "match": "exact"}]}]}
```

**result.json**（节选）：

```json
{
  "case_id": "demo-000",
  "status": "complete",
  "file_count": 3,
  "duplicate_groups": ["…同 versions.json…"],
  "version_chains": {"nodes": ["…"], "edges": ["…"], "clusters": ["…"]},
  "uncertainty": [],
  "change_records": ["ingest: 扫描 5 个文件，对象库新增 4 个对象，内容去重命中 1 次", "…"]
}
```
