# 科研资料库与文件管理 · 版本3：模板规则引擎归位

**核心思想：目录规范即配置。** Agent 不即兴决定任何归位/改名/路由——
一切由 `config/layout_template.json` 中的声明式规则决定。规则先行、
计划可审、落地可回滚、结果可核验。

- 纯 Python 3 标准库；全流程确定性脚本，**零模型请求**。
- 单文件失败不崩溃；不可读/坏压缩包/空目录全部显式登记，绝不静默。
- 元数据带出处 `{field, value, source, evidence}`；抽不到就 fallback +
  原因，**绝不猜**。

## 快速开始

```bash
python3 scripts/organize.py --input /input --work /app/work --output /app/output
# 或只出计划（dry-run，供人/Agent 审阅）：
python3 scripts/plan.py --input /input --work /app/work --dry-run
```

执行链：`organize.py`（编排）→ `rule_engine.py`（模板/路由/命名）→
`plan.py`（盘点+计划）→ `apply.py`（落地+journal）→ `audit.py`（重哈希+
覆盖率）→ `finalize.py`（result.json）。

## 目录结构

```
SKILL.md                       # 触发、执行协议、输出清单、异常表、边界
README.md                      # 本文件
config/layout_template.json    # 目录模板 + 字段字典 + 路由规则 + 命名策略
scripts/
  organize.py                  # 主入口（step0–step5 编排 + 约定翻译）
  rule_engine.py               # 规则引擎：load_rules/normalize/compute_target
  plan.py                      # 盘点 + dry-run plan.json
  apply.py                     # 落地 + journal.jsonl（可回滚）
  audit.py                     # 重哈希核对 + 规则覆盖率
  finalize.py                  # result.json（partial 先行，原子写）
references/
  output_contract.md           # result.json 契约与兼容形态
  edge_cases.md                # 16 类边界情况对照表
  rule_authoring.md            # 规则编写指南（本版本核心可复用资产）
schemas/
  result.schema.json           # result.json JSON Schema
  plan.schema.json             # plan.json JSON Schema
examples/minimal_example.md    # 虚构最小示例
CHANGELOG.md
```

## 可复用资产：把任意题目目录约定翻译成规则配置

这是本版本与其他版本最大的差异点（详见 `references/rule_authoring.md`）：

1. **识别约定**：`organize.py` step1 自动扫描 `task.md`/`case.json` 中
   `{a}/{b}/{c}` 形态的模板；如 `{topic}/{year}/{kind}/{name}`。
2. **翻译**：生成 `/app/work/layout_template.effective.json`——替换顶层
   模板、按 token 补字段字典（pattern + fallback）、全部路由规则改用
   题目模板。规则只决定"哪些文件匹配"，目录结构完全由题目约定决定。
3. **同义字段镜像**：`{topic}/{subject}` ← project，`{kind}/{category}` ←
   type，`{date}` ← year；元数据显式给出同义字段时以元数据为准，不猜值。
4. **手写新规则**：在 `route_rules` 加一条（唯一 id + priority + when
   条件 + target_template），dry-run 看 `rule_coverage` 复核，再 apply。

## 输出

- `/app/output/result.json`：case_id、output_contract 全部字段、status
  （partial/complete/complete_with_warnings）、sources、uncertainty、
  change_records。step0 先写 partial，终态原子写。
- `/app/output/library/`：按模板组织的资料库副本（源文件不动）。
- `/app/output/quarantine/`：空目录等隔离项。
- `/app/work/`：plan.json、journal.jsonl、audit.json、duplicates.json、
  versions.json、layout_template.effective.json（若发生约定翻译）。

## 异常处理

见 `SKILL.md` ④ 与 `references/edge_cases.md`。要点：冲突 `__dupN` 绝不
覆盖；坏压缩包登记 error 后照常归位本体；无权限项 `readable=false` 计
skipped；元数据缺失用 fallback 并记原因。

## 自查方法

在 `/tmp` 自建合成案例（中文名、改名副本=别名、两个历史版本 txt、
伴随 CSV 备注、管理备注 md、坏 zip + 好 zip、空目录、深层目录、
特殊字符文件名、chmod 000 无权限项），真实运行 `organize.py`：

```bash
# 合成输入（11 个文件 + case.json/task.md）见 CHANGELOG 自查节描述
python3 scripts/organize.py --input /tmp/skill3-test/input \
    --work /tmp/skill3-test/work --output /tmp/skill3-test/output
```

实际运行结果（2026-11-19，本仓库脚本真实输出）：

```
[plan]  files=11 planned=11 skipped=2 archives=2 empty_dirs=1 dup_groups=1 ver_groups=1 errors=1
[plan]  coverage: {"R03": 1, "R06": 6, "R01": 2, "R04": 2}        # 合计=11，无 DEFAULT 兜底
[apply] applied=11 failed=0 quarantined=1
[audit] verified=11/11 mismatches=0 missing=0 all_match=True
[audit] skipped_by_reason: {"task input file, not library content": 2}
[finalize] final result.json (status=complete, changes=14, uncertainty=3)
```

逐项核验点：

1. **零报错**：organize 退出码 0；单脚本亦可用 `python3 -m py_compile` 检查。
2. **plan 与 apply 一致**：plan 的 11 条 target 全部存在于 output，
   journal 记录 11 次 copy + 1 次 quarantine + 2 次 skip = 14 条 change_records。
3. **audit 全 match**：11/11 重哈希一致，`all_match=True`。
4. **覆盖率正确**：R01(压缩包)×2、R03(代码)×1、R04(数据)×2、R06(笔记)×6，
   合计 11=planned；skipped 的 2 条是 case.json/task.md（任务输入）。
5. **路由证据**：`实验数据/原始数据.csv` 依伴随 CSV 归位到
   `量子纠缠实验/2024/data/`（provenance: row 2 of 备注.csv）；
   `论文_v1.txt` 依管理备注归位到 `量子纠缠实验/2024/note/`；
   `数据集-2023.zip` 依文件名模式归位到 `数据集/2023/archive/`。
6. **重复/版本**：`报告_final.txt` 与 `报告_final-副本.txt` 同 sha256 →
   duplicates.json（别名）；`论文_v1→v2` 哈希不同 → versions.json，
   `superseded_by` 链 + size 差异 22 字节。
7. **边界**：坏 zip 登记 `BadZipFile` 进 uncertainty；空目录移入
   quarantine；`weird<name>?*.py` 规范化为 `weird_name___.py`；
   `会议 纪要：第(1)次.md` 的非法字符 `：` 替换为 `_`。
8. **约定翻译**：另测 `{topic}/{year}/{kind}/{name}` 模板被 step1 自动
   翻译（layout_template.effective.json），输出落在
   `unknown-topic/undated/doc/`（kind 由扩展名镜像）。
9. **冲突**：`A  B.txt` 与 `A B.txt`（不同内容）→ `A B.txt` + `A B__dup2.txt`，
   两文件内容各自完整（audit 通过）。
10. **无权限**：以 nobody 运行 plan.py，chmod 000 文件与目录分别登记
    `readable=false` + 原因（注：root 运行时不触发权限错误，故用
    setpriv 降权验证）。
