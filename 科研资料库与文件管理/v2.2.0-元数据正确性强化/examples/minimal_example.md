# 最小示例（虚构数据，仅作格式示例）

> 本页全部内容为**示例**，文件名与取值均为虚构，用于说明台账格式。

## 输入（虚构）

```
/input/
  case.json                       # {"case_id":"demo-001","required_fields":["title","year"], "output_contract":{"manifest_path":"","provenance_path":""}}
  项目X_王五_2022_实验记录.txt     # 正文首行：钙钛矿退火实验记录；含"仪器型号: XRD-6000"
  项目X_王五_2022_实验记录_副本.txt # 与上行内容相同（改名副本）
  元数据.csv                       # 文件名,标题,年份  →  项目X_王五_2022_实验记录.txt,钙钛矿退火实验,2022
```

## 运行

```bash
python3 scripts/provenance_pipeline.py --input /input --work /app/work --output /app/output
```

## 关键产物片段（虚构示例）

`provenance.jsonl` 一行：

```json
{"file": "项目X_王五_2022_实验记录.txt", "field": "year", "value": "2022",
 "source": "companion_table",
 "evidence": "companion '元数据.csv' row 2 col '年份' (encoding=utf-8-sig, matched '项目X_王五_2022_实验记录.txt') | corroborated by: filename",
 "confidence": 0.85, "conflicts": [],
 "rule": "priority: admin_note > companion_table > content > filename > agent_inference",
 "adjudicated_at": "2026-01-01T00:00:00+00:00"}
```

`duplicates.json` 一组：

```json
{"sha256": "…", "size": 812,
 "files": ["项目X_王五_2022_实验记录.txt", "项目X_王五_2022_实验记录_副本.txt"],
 "keep": "项目X_王五_2022_实验记录.txt",
 "note": "内容哈希一致判定为重复；按路径最短者保留主副本"}
```

`result.json` 骨架：

```json
{"case_id": "demo-001", "manifest_path": "manifest.json",
 "provenance_path": "provenance.jsonl",
 "status": "complete", "sources": ["manifest.json", "…"],
 "uncertainty": [], "change_records": ["…"]}
```
