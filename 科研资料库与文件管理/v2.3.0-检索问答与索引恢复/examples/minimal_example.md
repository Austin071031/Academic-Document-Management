# 最小示例（示例：以下 case、文件与输出均为虚构）

> 标注：**本页全部内容为演示用虚构示例**，不指向任何真实评测案例。

## 虚构输入 /input/case.json

```json
{
  "case_id": "demo_case_001",
  "output_contract": {
    "required_files": ["result.json", "archive/{case_id}_archive.tar.gz",
                       "archive/SHA256SUMS", "archive/MANIFEST.json"]
  },
  "searches": ["实验目的是什么"]
}
```

## 虚构输入 /input/task.md（节选）

```
请整理本资料库并交付归档。
保存期限：5年
密级：内部
```

（retention 抽出 `5年`、access_level 抽出 `内部`，均带 evidence。）

## 虚构资料库

```
/input/
├── 项目A/
│   ├── 实验记录_v1.txt      （旧版本）
│   ├── 实验记录_v2.txt      （新版本，多一行结论）
│   ├── 实验记录_v1.bak.txt  （与 v1 内容相同的改名副本）
│   ├── 备注 2026.csv        （管理性备注，含中文与空格）
│   └── data.zip             （含 inner.csv）
└── 空目录占位/
```

## 虚构运行

```bash
python3 scripts/archive_pipeline.py --input /input --work /app/work --output /app/output
# [archive-pipeline] organize: {"files_processed": 5, "skipped": 0, ...}
# [archive-pipeline] build_index: mode=fts5_bigram files=6 errors=0
# [archive-pipeline] verify_archive: ok {"match": 7, "mismatch": 0, ...}
# [archive-pipeline] finalize: status=complete
```

## 虚构关键产物摘录

`duplicates.json`（节选）：实验记录_v1.bak.txt 与 v1 哈希相同 →
`duplicate_of: 项目A/2026/text/实验记录_v1.txt`。

`versions.json`（节选）：`实验记录_v1.txt.superseded_by =
项目A/2026/text/实验记录_v2.txt`，`diff_summary: {added: 1, removed: 0}`。

`search_results.json`（节选）：问题"实验目的是什么"命中
`项目A/2026/text/实验记录_v2.txt` 第 2 行。

`result.json`（节选）：`status: complete`，`uncertainty: []`。
