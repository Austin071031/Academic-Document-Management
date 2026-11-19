# 最小调用示例（合成演示，非正式案例结果）

**输入（合成）**：`/input/proj/` 含三个文件：
`XT_report_v1.pdf`（3 页）、`XT_report_v2.pdf`（4 页，v2 新增一节）、
`old_copy_report.pdf`（与 v1 逐字节相同的改名副本）。

**调用**（核心两步）：

```bash
python3 $SKILL/scripts/lineage.py --work-dir /app/work
python3 $SKILL/scripts/retrieve.py --work-dir /app/work --query "buffer recipe" \
    --filter '{"exclude_sha256": <lineage.json 的 exclude_sha256>}'
```

**示意输出（节选，标注为示例）**：

```json
// lineage.json → clusters[0]
{
  "relation": "duplicate_exact",
  "canonical": "d003",
  "members": [
    {"path": "proj/XT_report_v2.pdf", "role": "canonical", "version_tags": ["v2"]},
    {"path": "proj/XT_report_v1.pdf", "role": "older_revision", "similarity_to_canonical": 0.72},
    {"path": "proj/old_copy_report.pdf", "role": "renamed_copy", "similarity_to_canonical": 1.0}
  ]
}
exclude_sha256: ["<v1的哈希>", "<副本的哈希>"]
```

检索只从 `XT_report_v2.pdf` 返回命中；answer 中"该配方存在于 2 处版本
（v1/v2 内容一致，副本不计）"。此演示数据为合成生成，仅说明接口与流程。
