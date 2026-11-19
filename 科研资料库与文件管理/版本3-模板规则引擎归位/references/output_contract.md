# 输出契约（output_contract 落实方式）

`result.json` 位于 `/app/output/result.json`，UTF-8、原子写（tmp + os.replace）。
任何时刻都存在：step0 先写 `status=partial`，step5 重写为终态。

## 必填核心字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `case_id` | string | 取自 `/input/case.json`；缺失时为 null 并记入 uncertainty |
| `status` | string | `partial` / `complete` / `complete_with_warnings`（有跳过项或核对不一致时诚实降级） |
| `sources` | array | 每项 `{source, evidence?, used_for}`：input_filesystem、sidecar_tables_and_notes、config/layout_template.json、case.json |
| `uncertainty` | array | 逐条列出：跳过项及原因、坏压缩包、核对不一致、失败操作、无法推导的契约字段；无则为 `["none: all files hashed and verified"]` |
| `change_records` | array | 来自 journal.jsonl 的 copy / quarantine / failed / skip 操作及 reverse |

## output_contract 兼容

`case.json.output_contract` 支持三种形态，均自动识别：

1. `{"required_fields": ["a","b"]}`（或键 `required` / `fields`）
2. `["a","b"]`
3. `{"a": ..., "b": ...}`（键即字段名）

能推导的契约字段如实填充（如 `library_dir`、`duplicates`、`versions`、
`rule_coverage`、`plan_file`、`audit_file`、`journal_file`、`counts`），
不能推导的置 `null` 并在 uncertainty 中说明，绝不编造。

## 配套工件（路径记录在 result.json.artifacts）

- `plan.json`：逐文件 `{source, target, action, rule_id, reason, size, sha256,
  metadata, metadata_provenance, field_values, notes}`。
- `journal.jsonl`：每行一条操作，copy 记录含 `reverse: {op: remove, path}`，
  quarantine 记录含 `reverse: {op: move_back, ...}`。
- `audit.json`：`{verified, mismatches, missing, rule_coverage, skipped_by_reason, all_match}`。
- `duplicates.json`：`{groups: [{sha256, paths: [...]}]}`。
- `versions.json`：`{groups: [{base, ext, count, size_delta_bytes, versions:
  [{path, version_token, size, sha256, superseded_by}]}]}`。
