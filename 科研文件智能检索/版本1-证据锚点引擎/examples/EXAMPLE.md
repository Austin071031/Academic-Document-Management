# 最小调用示例（合成演示，非正式案例结果）

**输入（合成）**：`/input/case.json` 指定 `case_id="demo-anchor"`，
`output_contract={answer, evidence, files, versions, failures, status}`；
`/input/papers/XT_report_v2.pdf` 为一篇 4 页报告，正文页脚印刷页码 21–24
（PDF 物理页 1–4，即 offset=+20）。

**调用**（命令见 SKILL.md 第 4 节）：

```bash
python3 $SKILL/scripts/inventory.py --input-root /input --work-dir /app/work
python3 $SKILL/scripts/extract.py   --input-root /input --work-dir /app/work
python3 $SKILL/scripts/pagefix.py   --work-dir /app/work
python3 $SKILL/scripts/segment.py   --work-dir /app/work
python3 $SKILL/scripts/retrieve.py  --work-dir /app/work --query "Tris-HCl buffer recipe" --topk 5
python3 $SKILL/scripts/verify.py    --work-dir /app/work
python3 $SKILL/scripts/report.py --skeleton  --input-root /input --work-dir /app/work --output-dir /app/output
# 补 answer 后
python3 $SKILL/scripts/report.py --finalize --input-root /input --work-dir /app/work --output-dir /app/output
```

**示意输出（节选，标注为示例）**：

```json
{
  "case_id": "demo-anchor",
  "status": "success",
  "answer": "Tris-HCl buffer 配方（50 mM Tris base、150 mM NaCl、pH 7.4）位于 XT_report_v2.pdf 的 2. Methods 节。",
  "evidence": [{
    "file_path": "papers/XT_report_v2.pdf",
    "sha256": "3f9a…（实测）",
    "version": "v2",
    "section_path": "2. Methods",
    "page": 2,
    "printed_page": 22,
    "paragraph_id": "d003-p0005",
    "quote": "The Tris-HCl buffer recipe is listed in Table 2: 50 mM Tris base, 150 mM sodium chloride, pH adjusted to 7.4 with hydrochloric acid (HCl)."
  }]
}
```

`pagefix.json` 中对应记录：`offset=20, offset_confidence=0.9,
offset_basis="arithmetic fit: offset=20, 4/4 pages"`——物理页 2 经校正为印刷页 22，
与页脚一致。此演示数据为合成生成，仅说明接口与流程。
