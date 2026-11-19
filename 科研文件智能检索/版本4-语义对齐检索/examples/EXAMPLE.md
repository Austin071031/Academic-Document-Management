# 最小调用示例（合成演示，非正式案例结果）

**输入（合成）**：文件库中中文笔记写"磷酸盐缓冲液（PBS）"，英文报告写
"phosphate buffered saline (PBS) stock"，另有仪器导出写 "PBS buffer, pH 7.2"。

**调用**：

```bash
python3 $SKILL/scripts/concepts.py --work-dir /app/work --aliases $SKILL/scripts/aliases.txt
python3 $SKILL/scripts/retrieve.py --work-dir /app/work --query "PBS 配方" \
    --concepts /app/work/concepts.json --topk 5
```

**示意输出（节选，标注为示例）**：

```json
// concepts.json（片段）
{"concepts": {
  "pbs": ["pbs", "磷酸盐", "phosphate", "buffered", "saline", "缓冲液"],
  "缓冲液": ["缓冲", "buffer", "buffering", "solution", "体系", "溶液"]
}}
// hits.json → hits[0]
{
  "score": 9.41,
  "matched_terms": ["pbs", "缓冲液", "buffer"],
  "anchor": {"file_path": "notes/实验笔记_2023.docx", "page": 1,
             "quote": "磷酸盐缓冲液（PBS）按 1× 母液稀释，调 pH 7.4"}
}
```

同一查询同时命中中文笔记与英文报告，`matched_terms` 记录对齐路径
（PBS→磷酸盐缓冲液；PBS→phosphate buffered saline），verify 逐字通过后入证据。
此演示数据为合成生成，仅说明接口与流程。
