# 最小示例（示例：全部为虚构数据）

> 本文件是演示性质的虚构示例，用于说明 plan.json 的一条 entry 长什么样。

## 输入（虚构）

```
/input
├── case.json          {"case_id":"demo-000","output_contract":{"required_fields":["library_dir"]}}
├── task.md            按 {project}/{year}/{type}/{name} 归档
├── 实验记录_2024.csv   （伴随 备注.csv 给出 project=可控核聚变, year=2024）
└── 笔记-副本.md        （与 笔记.md 内容完全相同 → 重复别名）
```

## 运行（示例）

```bash
python3 scripts/organize.py --input /input --work /app/work --output /app/output
```

## plan.json 中的代表条目（示例）

```json
{
  "source": "实验记录_2024.csv",
  "target": "library/可控核聚变/2024/data/实验记录_2024.csv",
  "action": "copy",
  "rule_id": "R04",
  "reason": "数据表归 data 区",
  "size": 128,
  "sha256": "9f2c...（64 位十六进制）",
  "metadata": {"project": "可控核聚变", "year": "2024", "type": "data"},
  "metadata_provenance": {
    "project": {"value": "可控核聚变", "source": "sidecar_csv", "evidence": "row 2 of 备注.csv"},
    "year": {"value": "2024", "source": "filename_pattern", "evidence": "regex group on filename"},
    "type": {"value": "data", "source": "sidecar_csv", "evidence": "row 2 of 备注.csv"}
  },
  "notes": []
}
```

重复文件 `笔记-副本.md` 会进入 `duplicates.json`（与 `笔记.md` 同 sha256）；
若另有 `笔记_v1.md`/`笔记_v2.md` 且哈希不同，则进入 `versions.json` 版本链，
`v1` 的 `superseded_by` 指向 `v2`。
