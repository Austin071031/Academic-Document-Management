# 规则编写指南（rule authoring）

本 Skill 的核心可复用资产：**目录规范即配置**。面对任意题目的目录约定，
改配置即可，不改代码。

## 1. 模板语法

顶层 `template` 与每条规则的 `target_template` 均为斜杠分隔路径，含
`{field}` 占位符，例如 `{project}/{year}/{type}/{name}`。

- 字段值来源优先级：伴随 CSV → 管理备注 md → 文件名模式 → 内置推导
  （year 从文件名正则 `(19|20)\d{2}`；type 从扩展名映射 `ext_type_map`）→
  fallback。
- 同义镜像：模板用 `{topic}`/`{subject}` 自动镜像 project，`{kind}`/
  `{category}`/`{doc_type}` 镜像 type，`{date}` 镜像 year（元数据显式给出
  同义字段时以元数据为准）。
- 抽不到的字段使用字段字典的 `fallback` 值，并在 plan notes 记原因；
  **绝不猜值**。

## 2. 字段字典（fields）

```json
"fields": {
  "project": {"pattern": "^...", "fallback": "unknown-project"},
  "type":    {"values": ["paper","data",...], "fallback": "other"}
}
```

- `values`：合法值白名单；越界 → fallback。
- `pattern`：正则校验；不匹配 → fallback。
- 两者可并用。所有落到 fallback 的情况都会写进 notes，可审计。

## 3. 路由规则与优先级

`route_rules` 为数组，每条：

```json
{
  "id": "R07",
  "priority": 65,
  "reason": "含 '原始数据' 的 csv 进 raw 数据区",
  "when": {"ext_in": ["csv"], "name_regex": "原始数据",
           "metadata": {"quality": {"regex": "raw|未处理"}}},
  "target_template": "{project}/{year}/data/raw/{name}"
}
```

`when` 支持的条件（全部可选，AND 关系）：

| 条件 | 语义 |
|---|---|
| `ext_in` / `ext_not_in` | 扩展名（大小写不敏感） |
| `name_regex` | 对文件名正则搜索 |
| `rel_regex` | 对输入相对路径正则搜索 |
| `min_size` / `max_size` | 字节数 |
| `metadata_has` | 这些元数据字段必须存在且非空 |
| `metadata` | `{field: "字面量"}` 或 `{field: {"regex": "..."}}` / `{"value": ...}` |

**第一条匹配生效**：按 `priority` 降序、id 字典序排序后自上而下匹配；
全部不命中走 `default_rule`。判定完全确定，同输入必得同计划。

## 4. 命名规范化（naming）

- Unicode NFKC（全角/兼容字符归一）。
- 非法字符 `<>:"/\|?*` → `_`；连续空白折叠为单空格；首尾点与空格裁剪。
- 分量 ≤ 80 字符、总路径 ≤ 240 字符（可在 `naming` 中调整）。
- Windows 保留名（CON、PRN、AUX、NUL、COM1-9、LPT1-9）自动加 `_` 前缀。
- 冲突追加 `__dup{n}`，**绝不覆盖**。

## 5. 如何加新规则

1. 在 `config/layout_template.json` 的 `route_rules` 追加一条，给定唯一
   `id` 与合适 `priority`（越大越先匹配；默认规则兜底，无需最高优先级）。
2. 需要新元数据字段时：在 `fields` 里补字段字典（pattern/values/fallback），
   并在 `filename_patterns`（带命名组的正则）或伴随表格列名中提供来源。
3. dry-run 复核：`python3 scripts/plan.py --input /input --work /app/work
   --dry-run`，检查 rule_coverage 与 entries 的 rule_id/notes。
4. 用 `scripts/audit.py` 复核覆盖率与哈希一致性后再 apply。

## 6. 题目约定翻译（step1 自动）

`organize.py` 自动扫描 task.md/case.json 中的 `{a}/{b}/{c}` 形态模板；
发现与默认模板不同的约定时，生成 `/app/work/layout_template.effective.json`
（模板替换、字段字典补 token 项、全部路由规则改用题目模板），
其余流程不变。手写翻译遵循同一原则：模板先行，规则只决定"匹配谁"。
