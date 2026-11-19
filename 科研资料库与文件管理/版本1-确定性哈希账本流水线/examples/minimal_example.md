# 最小示例（示例，非正式案例结果）

> 以下输入为虚构，输出为示意格式，仅说明流水线行为；不代表任何真实评测案例。

## 虚构输入 /input

```
/input/case.json                     {"case_id":"demo-001","output_contract":["summary","file_count"]}
/input/task.md                       整理资料库
/input/项目X_李四_2022_论文.txt      内容："摘要：……"
/input/论文-最终版.txt               与上面内容完全相同（改名副本）
/input/实验记录.csv                  a,b\n1,2
/input/备注.md                       "版本: v3"
```

## 运行

```bash
python3 scripts/library_pipeline.py --input /input --work /app/work --output /app/output
```

## 示意输出（节选）

library/ 树：

```
library/项目X/2022/文档/项目X_李四_2022_论文.txt
library/未分类项目/未知年份/数据/实验记录.csv
library/未分类项目/未知年份/文档/备注.md
```

- `论文-最终版.txt` 登记为 duplicate_of（不重复复制），见 duplicates.json：
  `{"sha256":"…","canonical":"项目X_李四_2022_论文.txt","aliases":["论文-最终版.txt"]}`
- versions.json：`chains=[]`（本例无多版本文档；改名副本是精确重复而非版本）。
- verify_report.json：`{"totals":{"expected":3,"match":3,"mismatch":0,"missing":0,"extra":0},"verdict":"PASS"}`
- result.json（Agent finalize 后）：

```json
{
  "case_id": "demo-001",
  "status": "success",
  "summary": "整理 5 个输入文件：入库 3 个，检出精确重复 1 个，无版本链，verify PASS。",
  "file_count": 3,
  "sources": [{"type": "verify_report.json", "path": "/app/output/verify_report.json"}],
  "uncertainty": ["无权限或缺失文件：无", "版本判定基于文件名相似度，完全改名的版本可能漏判"],
  "change_records": [{"action": "copy", "before": "实验记录.csv", "after": "未分类项目/未知年份/数据/实验记录.csv", "sha256": "…"}]
}
```
