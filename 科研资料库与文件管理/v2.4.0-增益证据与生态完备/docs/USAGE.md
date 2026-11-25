# USAGE — 完整调用说明（v2.4.0）

## 1. 环境要求

- Python 3.8+，**仅标准库**（json/os/re/hashlib/shutil/zipfile/tarfile/csv/
  unicodedata/argparse/subprocess/time/datetime）。无第三方依赖，无需联网。
- 对输入目录有读权限；对工作目录与输出目录有写权限。

## 2. 一条命令跑完整流水线

```bash
python3 scripts/organize.py --input /input --work /app/work --output /app/output
# 可选：
#   --rules config/layout_template.json   # 自定义规则配置
#   --case  /input/case.json              # 显式指定 case.json（默认在 --input 下找）
```

退出码：`0` 成功（允许带 warnings）；`1` 输入目录缺失；`2` 致命异常
（此时 /app/output/result.json 仍保留 partial 状态）。

### 评测环境标准调用（DeepSeek Harness）

```bash
python3 scripts/organize.py --input /input --work /app/work --output /app/output
```

输入：`/input/case.json`（case_id、output_contract，可能有
searches/questions/recovery）+ `task.md` + 混乱资料库。
输出：`/app/output/result.json`（case_id + output_contract 全字段 +
status/sources/uncertainty/change_records）及下表全部工件。

## 3. 分步调用（调试/人工审阅）

```bash
python3 scripts/plan.py  --input /input --work /app/work --dry-run   # 只出计划
python3 scripts/apply.py --input /input --work /app/work --output /app/output
python3 scripts/audit.py --work /app/work --output /app/output
python3 scripts/finalize.py --case /input/case.json --work /app/work --output /app/output
python3 scripts/qa.py       --input /input --work /app/work --output /app/output
python3 scripts/recover.py  --input /input --work /app/work --output /app/output
python3 scripts/gain_report.py --input /input --work /app/work --output /app/output
python3 scripts/preflight_check.py            # 提交契约自检（针对 Skill 目录本身）
```

## 4. 输入约定

| 输入 | 必需 | 说明 |
|---|---|---|
| `/input/case.json` | 建议 | `case_id`、`output_contract`（list / dict.required / dict.fields 三形态兼容）；可选 `searches`、`questions`、`recovery`、`layout` 等 |
| `/input/task.md` | 可选 | 若含 `{a}/{b}/{c}` 目录模板，step1 自动翻译进规则配置 |
| `/input/**` | 是 | 混乱资料库：中文/特殊字符文件名、改名副本、多版本、CSV/md 备注、zip/tar、深层目录、空目录均可 |

`case.json` 可选字段形态（qa/recover 均做宽松解析）：

```json
{
  "searches": ["量子纠缠 退相干", {"query": "数据采集协议"}],
  "questions": ["实验的采样率是多少？"],
  "recovery": ["报告_final.txt", {"sha256": "<64hex>"}, {"filename": "数据.csv"}]
}
```

## 5. 输出清单

| 路径 | 内容 |
|---|---|
| `/app/output/result.json` | 契约结果：case_id + output_contract 全字段 + status/sources/uncertainty/change_records（partial 先行、原子写） |
| `/app/output/library/<按模板>` | 组织后的资料库副本（源文件不动） |
| `/app/output/quarantine/` | 空目录等隔离项 |
| `/app/output/gain_report.md` / `gain_metrics.json` | 可机检增益度量：计数、前后对照、耗时、幂等验证（全部真实计数） |
| `/app/output/search_results.json` | 检索/问答命中（文件+行号+片段）或诚实 `no_evidence` |
| `/app/output/recovery_log.jsonl` + `recovered/` | 恢复登记（recovered / not_found / error + 校验哈希） |
| `/app/work/plan.json` | dry-run 计划（源→目标、规则编号、元数据出处） |
| `/app/work/journal.jsonl` | 操作账本，每条含 reverse（可回滚） |
| `/app/work/audit.json` | 重哈希核对 + 规则覆盖率 |
| `/app/work/duplicates.json` / `versions.json` | 重复分组 / 版本链 |
| `/app/work/run_timing.json` | 各 step 与全流程真实耗时 |
| `/app/work/layout_template.effective.json` | 题目约定翻译后的规则（若发生） |

## 6. 限制（诚实声明）

- **复制保源**：输出是组织副本，不就地改名/删除源（空目录除外——移入
  quarantine，journal 带 move_back 反向记录）。
- 压缩包只登记清单不解包归位（rar/7z 仅登记，stdlib 不支持解包）；
  recover 可按成员名单个解出 zip/tar 内文件。
- 检索为字面/词元匹配（CJK 二元组 + 拉丁词），无语义向量；>2MB 的
  单文件不建全文索引（仍可文件名命中）。
- 元数据三路解析（文件名模式/伴随 CSV/管理备注 md）之外不做内容猜测；
  抽不到一律 fallback + 原因。
- 评测输入之外的目录不做任何写操作。

## 7. 失败处理

| 情况 | 行为 |
|---|---|
| 单文件不可读/无权限 | 登记 `readable=false` + 原因，计 skipped，继续 |
| 坏 zip / 不支持格式 | 登记 error 进 archives/uncertainty，本体照常归位 |
| 目标路径冲突 | `__dupN` 递增，绝不覆盖 |
| 中途崩溃 | 兜底保留 partial result.json；qa/recover/gain_report 任一步失败只登记，不影响 result.json 已确定结论 |
| 检索无命中 / 恢复找不到 | `no_evidence` / `not_found` + 原因，绝不编造 |

## 8. 自查方法

1. 本地合成夹具（见 README「自查方法」与 CHANGELOG v2.4.0 节）跑两次
   入口，确认退出码 0、两次 `gain_metrics.json` 条目哈希一致。
2. `python3 scripts/preflight_check.py` 全 pass（退出码 0）才允许提交。
3. 逐项核对：`audit.json` 的 `all_match==true`；`gain_metrics.json` 的
   `idempotency.idempotent==true`；`search_results.json` 命中带行号。
4. 复跑核对命令清单见 `references/reproduce.md`。
