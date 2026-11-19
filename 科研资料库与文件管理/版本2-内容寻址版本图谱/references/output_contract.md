# output_contract 处理契约

## 规则

`result.json` 必须包含 `/input/case.json` 中 `output_contract` 声明的**全部字段**，
外加 `case_id`，并始终附带 `status`、`sources`、`evidence`、`uncertainty`、
`change_records`、`artifacts`。

## 契约字段解析（finalize.py）

- `output_contract` 为 list：条目可以是字符串字段名，或 `{"field"/"name": ...}` 字典；
- 为 dict：取其键作为字段名；
- 缺失/非法：按空契约处理（result.json 仍含通用字段）。

## 字段填充启发式（按字段名，大小写不敏感）

| 字段名包含 | 填充内容 |
|---|---|
| `status` / `状态` | 运行状态（complete / complete_with_warnings / partial / error） |
| `file`/`文件` + `count`/`num`/`total`/`数` | 已索引文件数（int） |
| `file`/`文件`（列表义） | 文件清单（path、logical_path、sha256、size、mtime） |
| `dup` / `重复` / `别名` / `alias` | duplicate_groups（content_id + 全部路径；带 count 词则给数量） |
| `version` / `版本` / `lineage` / `谱系` / `chain` | 版本谱系 nodes/edges/clusters（带 count 词则给簇数） |
| `search` / `检索` / `查询` / `keyword` | search_results.searches（每条命中带 文件+行号+片段） |
| `question` / `问题` / `answer` / `答案` / `qa` | search_results.questions（top-5 证据片段） |
| `tree` / `struct` / `结构` / `目录` / `hierarch` | 规范目录路径清单（去重排序） |
| `index` / `索引` | index.json 路径 + 统计 |
| `summary` / `摘要` / `概览` / `overview` | 一句话运行摘要 |
| 其它无法映射 | **null** + 在 uncertainty 中说明"无法映射，已置 null（不编造）" |

## status 语义（诚实）

- `complete`：全链路成功且无警告；
- `complete_with_warnings`：结果完整但存在坏压缩包、跳过文件、步骤异常等（uncertainty 列出）；
- `partial`：ingest 后立即写入的保底版本（后续步骤失败时停留在此状态）。

## 顶层固定字段

- `sources`：每个输入文件 `{path, sha256(前16位), origin, readable}`；
- `evidence`：关键证据指针抽样（重复组、supersedes 边、检索命中数），完整数据在 `library/`；
- `uncertainty`：不可映射契约字段、跳过文件+原因、坏包、步骤异常；
- `change_records`：本次运行全部动作流水（入库/去重/改名冲突/谱系/检索/写结果）；
- `artifacts`：各产物相对路径。

结构校验见 `schemas/result.schema.json`。
