# REUSE — 把本 Skill 复用到你自己的资料库（v2.4.0）

本版本的全部决策都是"配置 + 确定性脚本"，**不绑定任何具体题目**。
以下四块资产可独立复用。

## 1. 目录模板（config/layout_template.json）

复制该文件，改 4 处即适配新资料库：

```json
{
  "template": "{project}/{year}/{type}/{name}",   // ① 你的目标目录形态
  "fields": { ... },                               // ② 每个模板变量的字段字典
  "route_rules": [ ... ],                          // ③ 路由规则（见下）
  "naming": { "max_component_chars": 80, ... }     // ④ 命名约束
}
```

- 模板变量任意命名：`{topic}/{year}/{kind}/{name}`、`{lab}/{date}/{name}` 都行；
  未在 `fields` 中声明的变量由规则引擎按同义词镜像（topic←project、
  kind←type、date←year），不猜值。
- 每个字段声明 `pattern`（正则白名单）与 `fallback`（抽不到时的占位值），
  引擎自动校验+记原因。

## 2. 字段字典（fields）与扩展名映射（ext_type_map）

- `fields.<name>.values`：枚举白名单（如 type: paper/data/code/...），值不在
  字典里 → 用 fallback 并在 notes 记原始值。
- `ext_type_map`：扩展名 → 类型。加你自己的类型（如 `.ipynb`→`notebook`）
  只需一行。
- `filename_patterns`：从文件名抽字段的命名捕获正则，
  如 `^(?P<project>.+?)[-_](?P<year>(19|20)\d{2})`。

## 3. 路由规则（route_rules）

每条规则四要素，**priority 降序、第一条匹配生效**：

```json
{
  "id": "R07",                    // 唯一 id，审计报告按它统计覆盖率
  "priority": 65,                 // 越大越先匹配
  "reason": "发票归财务区",        // 人读理由，进 plan.json
  "when": {"ext_in": ["pdf"], "name_regex": "发票|invoice"},
  "target_template": "{project}/{year}/finance/{name}"
}
```

`when` 支持：`ext_in` / `ext_not_in` / `name_regex` / `rel_regex` /
`min_size` / `max_size` / `metadata_has` / `metadata`（含 regex/value 条件）。
写新规则的标准流程（详见 `references/rule_authoring.md`）：

1. 加规则 → 2. `plan.py --dry-run` 看 `rule_coverage` 是否按预期命中 →
3. 无 DEFAULT 异常兜底后 `apply.py` → 4. `audit.py` 核对。

## 4. 脚本的独立复用

| 脚本 | 复用方式 |
|---|---|
| `rule_engine.py` | 纯函数库：`load_rules / normalize_filename / compute_target / unique_path`，可 import 进任何 Python 项目 |
| `plan.py` | `build_plan(input_dir, cfg)` 直接返回盘点+计划字典；CLI 出 plan.json |
| `apply.py` / `audit.py` | 读 plan.json 落地/核对，journal 带 reverse 可回滚 |
| `qa.py` | 任何文本目录都能检索：`--output` 指向的 library 或退回 `--input`；无 case.json 时 queries=0，安全空转 |
| `recover.py` | 只要有 plan.json（账本）就能按 文件名/sha256 恢复并校验；无恢复请求时只写空日志 |
| `gain_report.py` | 任何跑完 plan/apply/audit 的工作区都能出增益报告；幂等复算需 `--rules` 指向生效配置 |
| `preflight_check.py` | 对任意目录做提交约束体检：`python3 preflight_check.py --root <dir> --out <report.json>` |

### 最小接入示例（自己的资料库）

```bash
cp -r config scripts /path/to/your/toolkit/
$EDITOR /path/to/your/toolkit/config/layout_template.json   # 改模板与规则
python3 /path/to/your/toolkit/scripts/organize.py \
    --input /path/to/messy_library \
    --work /tmp/work --output /tmp/out \
    --rules /path/to/your/toolkit/config/layout_template.json
```

## 5. 复用时的注意点

- 全部脚本仅标准库、UTF-8 安全（中文/特殊字符文件名先 NFKC 再替换非法字符）。
- `TASK_INPUTS = {'case.json', 'task.md'}`（plan.py）：非评测场景可忽略，
  这两文件会被计为 skipped 而非归位。
- 元数据出处 `{value, source, evidence}` 三元组贯穿 plan.json，引用数据时
  可直接溯源到"伴随 CSV 第 N 行 / 管理备注提及行"。
- gain_report 的所有数字都从工件实时计数——不要把报告当模板手填，
  重跑脚本即可再生。
