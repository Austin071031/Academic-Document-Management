# output_contract 与 result.json 处理规则

## 1. 合同字段优先

case.json 中的 `output_contract`(也可能叫 `outputContract`、`required_outputs`、`outputs`)定义了本案例 result.json 必须包含的字段。**合同字段一个不能少、名字不能改**;kb_result.py 会自动:

1. 解析合同字段清单(兼容三种形态:JSON Schema 的 properties、字段名字符串数组、`{"name": ..., "type": ...}` 对象数组);
2. 以 answers.json 中同名字段填充;未填的留 null 并记入 `missing_contract_fields`;
3. 追加复核支撑字段(case_id、status、sources、uncertainty、questions_without_evidence、conflicts、change_log、library_stats、provenance)。

若合同本身给出了示例结构,按示例结构组织字段值。

## 2. status 取值

- `complete`:合同字段全部填上,证据齐备,无未解决的异常。
- `partial`:部分完成——存在缺证问题、不可读关键文件、或时间预算耗尽,但已交付部分可核验;必须在 `missing_contract_fields` / `questions_without_evidence` / `change_log` 中说明。
- `failed`:输入缺失(如无资料库、case.json 不可读)或流水线整体失败;说明失败阶段与原因。

## 3. 与输入一一对应

- 资料结果类字段(目录/清单/元数据/版本关系)必须能追溯到 inventory.json / versions.json 的条目,不新增不存在的文件,不遗漏输入文件(被排除的须说明理由并登记在 change_log)。
- 操作证据类字段(哈希/权限/日志)直接取自 inventory.json 与 ops_log.jsonl。
- 失败与恢复类字段(跳过/冲突/重复/恢复)取自异常清单与 conflicts。

## 4. change_log 条目格式

```json
{"ts": "...", "action": "excluded_from_index", "target": "draft/old_notes.txt",
 "reason": "被 version_notes.md 明确标记为废弃草稿", "recovered": false}
```
