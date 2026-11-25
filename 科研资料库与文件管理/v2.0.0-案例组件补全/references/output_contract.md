# result.json 输出契约

result.json 必须满足：

1. **顶层必含** `case_id`（来自 /input/case.json，逐字一致）与 `status`。
2. **output_contract 字段逐项覆盖**：把 case.json 中 `output_contract`（list 或 dict）里的每个字段名作为顶层键出现。值由 Agent 依据脚本产物填写；脚本生成的 partial 模板已逐项置 `null` 并列入 `_pending_fields`。
3. **诚实性三件套**：
   - `sources`：数组，至少含 inventory.jsonl / operation_log.jsonl / verify_report.json 的路径条目，可追加 manifest、duplicates、versions、search_results.json、recovery_log.jsonl（v2）。
   - `uncertainty`：数组，逐条声明未覆盖/未确定事项（如跳过文件数、版本漏判风险、元数据 null 字段）。
   - `change_records`：数组，来自 operation_log.jsonl 的近期操作记录（before/after/sha256/action/time/status）。
4. **状态机**：`partial`（early）→ Agent 补叙述 → `verify` PASS 后 `finalize_result.py` 自动置 `success`；verify FAIL 或有跳过文件保持/回退 `partial` 并说明。

## 字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| case_id | string | 与 case.json 完全一致 |
| status | string | partial / success / failed |
| sources | array[{type,path}] | 证据出处 |
| uncertainty | array[string] | 不确定性声明，禁止为空数组装作确定 |
| change_records | array[object] | 操作日志摘录 |
| verify | object | finalize 时自动合并：{verdict, totals, report} |
| <output_contract 各字段> | any | Agent 按题目要求填；必须可追溯到 manifest/duplicates/versions 中的具体证据 |

## 反模式（判负风险）

- 缺 case_id 或任一 output_contract 字段（validate_result.py 会拒绝，退出码 1）。
- status=success 但 verify_report verdict=FAIL。
- 元数据字段无 source/evidence 支撑的值（"agent 猜测"）。
- 把跳过文件计入"已完成"。
