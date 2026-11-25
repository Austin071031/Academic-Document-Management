# 归档包规范（archive/ 四件套字段定义）

## 1. `<case_id>_archive.tar.gz`

- gzip 压缩 tar，成员路径相对 `library/` 根（POSIX `/` 分隔）；
- 普通文件 + 目录成员均含；uid/gid 归零（uname/gname 置空）；
- UTF-8 文件名原样保留（含中文与特殊字符）。

## 2. SHA256SUMS

逐文件哈希清单，每行：

```
<64位小写sha256><两个空格><相对library根的路径>
```

- 按路径排序；空库时为 0 行空文件；
- 校验：`sha256sum -c SHA256SUMS`（解包后于根目录执行）。

## 3. MANIFEST.json

```json
{
  "case_id": "string",
  "archive_format": "tar.gz",
  "archive_file": "<case_id>_archive.tar.gz",
  "created_utc": "ISO8601 UTC",
  "file_count": 0,
  "member_count": 0,
  "retention":    {"value": "...", "source": "...", "evidence": "..."},
  "access_level": {"value": "...", "source": "...", "evidence": "..."},
  "pack_errors": [],
  "files": [
    {
      "path": "项目/2026/text/xxx.md",
      "size": 123,
      "sha256": "...",
      "mode": "0o644",
      "source": {"original_relpath": "...", "provenance": [
        {"field": "retention", "value": "...", "source": "...", "evidence": "..."}
      ]},
      "retention": "...",
      "retention_source": "...",
      "access_level": "...",
      "access_level_source": "..."
    }
  ]
}
```

字段约束：

- `retention.value`/`access_level.value`：从 case.json/task.md 正则
  抽取；抽不到为 `"unspecified"`，`source` 为 null，且必须在
  HANDOFF_README 与 result.uncertainty 中说明；
- `source.provenance` 每项四元组 `{field,value,source,evidence}`，
  evidence 必须指回可复核的抽取片段或脚本登记。

## 4. HANDOFF_README.md

固定章节：归档标识 / 内容清单 / 校验方法 / 恢复步骤 /
保存期限与权限范围 / 备注。面向半年后接手的人，不依赖本仓库即可
完成校验与恢复。

## 5. verify_report.json（校验产物，独立生成）

```json
{
  "case_id": "...", "archive_file": "...",
  "verified_utc": "...", "status": "ok|mismatch|missing|extra|failed",
  "counts": {"match": 0, "mismatch": 0, "missing": 0, "extra": 0, "unreadable": 0},
  "details": [{"kind": "...", "path": "...", "expected_sha256": "...", "actual_sha256": "...", "reason": "..."}],
  "method": "extract to tempdir, per-file sha256 vs SHA256SUMS"
}
```

- status=ok  ⟺  match>0 且 mismatch=missing=0（extra 单独上报并降级）；
- 解包前逐成员 realpath 校验，路径穿越成员拦截并登记 blocked。
