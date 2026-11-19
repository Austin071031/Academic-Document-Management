# output_contract 回应规范

## case.json 中的形态

评测输入 `/input/case.json` 含 `output_contract` 字段，可能形态：

1. **字典**：`{"required_files": ["archive/xxx.tar.gz", "result.json"], ...}`
   —— 已知键 `required_files/files/deliverables/required_deliverables/
   outputs/artifacts` 视为产物清单，逐条检查存在性；其余键原样回应
   （`handled=passthrough`），不编造值。
2. **列表**：`["result.json", "library/"]` —— 逐条检查存在性。
3. **其他/缺失**：原样回应并在 note 中说明，同时交付默认清单。

模板占位：清单项可含 `{case_id}`，展开后再检查。

## result.json 必填字段（本 Skill 保证）

```json
{
  "case_id": "string",
  "status": "complete | partial | error",
  "output_contract": {"raw": ..., "fields": {"<每个 contract 字段的回应>"}},
  "deliverables": {"<名称>": {"path": "...", "exists": true}},
  "sources": [{"source": "...", "role": "..."}],
  "uncertainty": ["..."],
  "change_records": [{"step": "...", "ok": true, "...": "..."}],
  "summary": {"organize": ..., "verify": ..., "searches": ...}
}
```

## 诚实性规则

- `exists` 一律真实检查文件系统，不预设 true；
- 校验未通过（verify.status != ok）时 status 不得为 complete；
- 抽不到的信息（retention/access_level/语义答案）一律
  `"unspecified"` + uncertainty 说明，禁止编造；
- `partial` 不是失败：step0 即写 partial，保证任何中断都有交付。
