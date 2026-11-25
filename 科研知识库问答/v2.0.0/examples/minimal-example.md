# 最小调用示例(合成数据,仅示意接口与流程)

> 本示例所有文件名、哈希、问答内容均为虚构,仅说明各阶段命令与产物形态,不代表任何正式案例结果。

## 输入(示意)

```json
// /input/case.json(节选,示意)
{
  "case_id": "demo-001",
  "library": "/input/library",
  "task": "回答两个问题,每个论断给出文件、版本、页码/段落与原文摘录。",
  "questions": ["催化剂 X 的最优反应温度是多少?"],
  "output_contract": ["answers", "inventory_summary", "version_report", "issues"]
}
```

资料库 `/input/library` 含:`catalyst_X_v1.pdf`、`catalyst_X_v2.pdf`(v2 取代 v1)、
`catalyst_X_v1_backup.pdf`(v1 的重复副本)、`notes_readme.md`(管理方说明)。

## 运行(实际命令)

```bash
mkdir -p /app/work /app/output
python3 /skills/weekly-skill/scripts/kb_inventory.py --roots /input/library --work /app/work
python3 /skills/weekly-skill/scripts/kb_extract.py --inventory /app/work/inventory.json --root /input/library --work /app/work
# 读 notes_readme.md 发现"以 v2 为准" -> 写 version_rules.json
python3 /skills/weekly-skill/scripts/kb_versions.py --inventory /app/work/inventory.json --work /app/work --rules /app/work/version_rules.json
python3 /skills/weekly-skill/scripts/kb_index.py --work /app/work
python3 /skills/weekly-skill/scripts/kb_search.py --work /app/work --query "最优反应温度 催化剂 X" --topk 8
# 依据命中段落撰写 /app/work/answers.json(见 references/citation-and-evidence.md)
python3 /skills/weekly-skill/scripts/kb_result.py --case /input/case.json --answers /app/work/answers.json --work /app/work --outdir /app/output
```

## 示意输出(节选,虚构)

```json
// /app/output/result.json(节选)
{
  "case_id": "demo-001",
  "status": "complete",
  "answers": {
    "q1": {
      "answer": "催化剂 X 的最优反应温度为 280 °C,此时转化率最高 [E1]。",
      "claims": [
        {"text": "最优反应温度为 280 °C", "evidence": ["E1"]}
      ],
      "evidence": [{
        "id": "E1",
        "path": "catalyst_X_v2.pdf",
        "version_label": "v2",
        "canonical": true,
        "page": 4,
        "para_index": 2,
        "exact_quote": "……(虚构摘录)……"
      }],
      "uncertainty": "A"
    }
  },
  "questions_without_evidence": [],
  "missing_contract_fields": [],
  "library_stats": {"files": 4, "unreadable": 0, "duplicate_groups": 1, "needs_ocr": 0}
}
```
