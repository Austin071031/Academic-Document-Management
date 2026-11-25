---
name: research-library-rule-engine-v2-4
description: 模板规则引擎驱动的科研资料库组织：目录规范即配置，plan/apply/audit 确定性归位；含可机检增益度量（前后对照+幂等验证）、检索问答、恢复操作与提交契约自检，零模型请求。
---

# 科研资料库与文件管理 · v2.4.0：模板规则引擎归位 + 增益证据与生态完备

## ① 触发与适用

当任务要求把一个乱糟糟的科研资料库（中文与特殊字符文件名、改名备份副本、
多历史版本、伴随元数据表、管理备注、zip/tar 压缩包、深层目录、不可读文件、
空目录）整理成结构化目录树，并产出可核验的结果清单（result.json）时使用本 Skill。

适用判断：输入是"文件目录 + 可能的题目目录约定"。只要最终要"归位/路由/改名/
去重/版本梳理"，即适用。纯问答、纯文献检索、无需动文件的任务不适用（见⑤）。

## ② 执行协议

一切归位/改名/路由由规则决定，Agent 不即兴决策。主入口：

```bash
python3 scripts/organize.py --input /input --work /app/work --output /app/output \
    [--rules config/layout_template.json]
```

- **step0 检查**：确认 `/input` 存在；立即写 `partial` 状态的
  `/app/output/result.json`（任何时刻 result.json 都存在且自洽）。
- **step1 约定翻译**：若 `case.json`/`task.md` 指定了不同的目录约定
  （如 `{topic}/{year}/{kind}/{name}`），先把题目规则翻译进配置——
  规则即约定：改写模板与字段字典，产出
  `/app/work/layout_template.effective.json` 供后续步骤使用。
  同义字段（topic/project、kind/type 等）自动镜像，不猜值。
- **step2 plan（dry-run）**：`scripts/plan.py --dry-run` 盘点输入（流式
  sha256、可读性登记、zip/tar 展开登记、空目录登记、三路元数据解析带出处
  合并、重复与版本识别），由 rule_engine 逐文件计算目标路径，生成
  `plan.json`（每条含 源路径→目标路径、命中规则编号、原因）、
  `duplicates.json`、`versions.json`。此步只出计划，不落地。
- **step3 apply**：`scripts/apply.py` 按计划复制到
  `/app/output/library/`（绝不移动/删除源），写 `journal.jsonl`
  （每条含 reverse 操作，可回滚）；空目录移入 `/app/output/quarantine/`；
  目标冲突追加 `__dupN`，绝不覆盖。
- **step4 audit**：`scripts/audit.py` 对落地文件重哈希核对，输出规则
  覆盖率报告（多少文件命中哪条规则、多少落入 DEFAULT、多少跳过及原因）。
- **step5 finalize**：`scripts/finalize.py` 写最终 `/app/output/result.json`：
  `output_contract` 全部字段 + `case_id` + 诚实的
  `status`/`sources`/`uncertainty`/`change_records`。
- **step6 qa**（v2.4.0）：`scripts/qa.py` 回答 `case.json` 的
  `searches`/`questions`——对 library 建倒排索引，命中带 文件+行号+片段，
  无命中诚实 `no_evidence`；写 `/app/output/search_results.json`。
- **step7 recover**（v2.4.0）：`scripts/recover.py` 处理 `case.json` 的
  `recovery` 请求——按文件名/哈希从账本与压缩包登记中恢复、重哈希校验，
  写 `/app/output/recovered/` 与 `/app/output/recovery_log.jsonl`；
  找不到诚实 `not_found`。
- **step8 gain_report**（v2.4.0）：`scripts/gain_report.py` 从工件实时
  计数生成 `/app/output/gain_report.md` + `gain_metrics.json`——归位条目、
  精确去重合并条目、版本链边、恢复/检索操作数、脚本耗时、模型调用=0、
  幂等复算哈希对照、整理前混乱度 vs 整理后可核验质量。

预算纪律：全流程为确定性脚本，零模型请求；64 次请求/900 秒预算全部留给
题目中真正需要推理的部分（若有）。

## ③ 输出清单

| 路径 | 内容 |
|---|---|
| `/app/output/result.json` | case_id、output_contract 字段、status、sources、uncertainty、change_records |
| `/app/output/library/<按模板>` | 组织后的资料库（复制，非移动） |
| `/app/output/quarantine/` | 空目录等被隔离项 |
| `/app/work/plan.json` | dry-run 计划：源→目标、规则编号、原因、元数据出处 |
| `/app/work/journal.jsonl` | 操作日志，含 reverse（可回滚） |
| `/app/work/audit.json` | 重哈希核对结果 + 规则覆盖率 |
| `/app/work/duplicates.json` | 内容哈希重复分组（改名备份副本=别名） |
| `/app/work/versions.json` | 多历史版本链（superseded_by + 差异摘要） |
| `/app/work/run_timing.json` | 各 step 与全流程真实耗时（v2.4.0） |
| `/app/output/gain_report.md` / `gain_metrics.json` | 可机检增益度量 + 前后对照 + 幂等验证（v2.4.0） |
| `/app/output/search_results.json` | searches/questions 命中（文件+行号+片段）或 no_evidence（v2.4.0） |
| `/app/output/recovery_log.jsonl` + `recovered/` | 恢复操作登记与校验结果（v2.4.0） |

提交前自检：`python3 scripts/preflight_check.py` 核验 frontmatter/文件数/
大小/UTF-8/无符号链接/无密钥模式，输出 `preflight_report.json`（退出码非 0
即不满足提交契约，先修复再提交）。复跑核对命令见 `references/reproduce.md`。

## ④ 异常处理对照表

| 情况 | 处理 |
|---|---|
| 单文件读失败/无权限 | 登记 `readable=false` + 原因，计 skipped，继续其余文件；os.walk 不可读目录经 onerror 显式登记，绝不静默 |
| 目标路径冲突（规范化后同名） | 追加 `__dupN`（N 从 2 递增），绝不覆盖 |
| 坏 zip / 不支持压缩格式 | 登记 error 与原因进 archives/uncertainty，文件本体照常按规则归位 |
| 空目录 | 移入 quarantine 并在 journal 记 reverse |
| 元数据抽不到 | 字段用 fallback 值并在 notes/uncertainty 记原因，绝不猜 |
| 字段值不在字段字典 | 用字段字典 fallback 值，notes 记录原始值与原因 |
| 死链/异常文件名 | NFKC + 非法字符替换 + 空白折叠 + 截断；单文件异常不崩溃 |
| 中途崩溃 | 兜底 handler 尽力保留/重写 partial result.json；result.json 原子写 |

## ⑤ 不适用边界

- 纯问答、文献检索、不涉及文件系统整理的任务。
- 要求"就地重命名源目录"而非"产出组织副本"的任务（本 Skill 默认复制保源，
  回滚语义清晰；如题目强制原地操作，需在规则层显式改动并承担风险）。
- 需要联网下载、调用外部服务或非标准库依赖的任务（本 Skill 仅 Python 3 标准库）。
- 评测输入之外的目录不做任何写操作。
