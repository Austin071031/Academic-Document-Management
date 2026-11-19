# CHANGELOG

## 4.0.0（版本4：元数据溯源台账 / provenance-first metadata ledger）

### 架构区分要点（与其他版本的差异）

1. **字段字典先行**：`config/field_dictionary.json` 是管线宪法——字段定义、合法来源
   白名单、格式、必填项、别名、文件名/内容正则全部外置；评测题目指定的必需字段在
   step1 合并进字典 `required`，覆盖率报告按字典统计。换库只改配置不改代码。
2. **逐字段台账 + 冲突留痕**：每个 (文件, 字段) 最终值都是一条
   `provenance.jsonl` 记录（value/source/evidence/confidence/conflicts/rule/时间戳），
   落选候选的证据不丢弃、裁决规则串内嵌每行，产物自证清白；
   `manifest.csv` 每字段带 `__source` 出处列。
3. **Agent 推断被制度性降级**：`agent_inference` 固定最低优先级（0.50），
   必须附所见依据，任何脚本证据来源均可覆盖；Agent 补录走
   `agent_candidates.jsonl` → 重跑 adjudicate+build_manifest 的标准通道，
   与脚本产出同槽裁决，不搞"Agent 特权覆盖"。

### 功能

- 9 个 Python3 标准库脚本：ledger_common（共享层）、provenance_pipeline（编排+扫描
  +zip/tar 展开）、extract_from_filename、extract_from_content（前 64KB 嗅探 +
  可选 pdftotext）、join_companion、parse_admin_notes、adjudicate、build_manifest、
  finalize（--partial 先行 / --final 汇总）。
- 重复：流式 sha256 内容判定 → duplicates.json；版本：管理备注 superseded_by 事实
  优先、归一化主干+mtime 启发式兜底 → versions.json（带差异摘要）。
- result.json：case_id + output_contract 全键（无产物可填置 null 且 uncertainty
  说明）+ status/sources/uncertainty/change_records（六要素）。
- 异常全覆盖：无权限、坏 zip、空目录、深目录、编码混乱（utf-8/gb18030/utf-16
  依次尝试并记录）、PDF 无文本层、伴随表幽灵行——全部登记不静默。

### 自查记录

在 /tmp 合成案例（中文名、改名副本、两版本 txt、CSV 管理备注含替代关系、伴随元数据
CSV 含幽灵行、坏 zip、空目录、五层深目录、GBK 编码文件、case.json 指定
required_fields 与 output_contract 五键）真实运行管线：全部子步骤 rc=0，
provenance.jsonl 逐字段带来源与冲突留痕、伴随表覆盖文件名冲突值、重复组与版本链
正确、异常项全数进 uncertainty、status=complete。详见 README.md §7。
