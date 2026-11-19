# 最小调用示例（合成演示，非正式案例结果）

**输入（合成）**：与核心流水线示例相同的库，其中含 1 个无文本层扫描件。

**调用**：

```bash
# …inventory / extract / segment / retrieve / verify / report(--skeleton, 补 answer, --finalize)
python3 $SKILL/scripts/audit.py --input-root /input --work-dir /app/work --output-dir /app/output
```

**示意输出（标注为示例）**：

```
audit overall=pass
  gate1 evidence_verified     PASS — 5 evidence, 0 unverified
  gate2 contract_complete     PASS — fields=6 missing=0 null_required=0
  gate3 status_honest         PASS — status=partial failures=1
  gate4 manifest_consistent   PASS — outputs=6 mismatch=0
  gate5 journal_coverage      PASS — core steps covered: 6/6
```

对应 `audit_report.json` 含 `limitations: []` 与复跑命令清单；`manifest.json`
登记 6 个输出文件的 sha256；`changes.json` 记录与上次运行的差异；
`run_journal.jsonl` 追加 30+ 条操作记录，扫描件的 `no_text_layer_ocr_unavailable`
失败如实保留，因此 status=partial 而非 success。此演示数据为合成生成，仅说明
接口与流程。
