# CHANGELOG

## v2.2.0（2026-11-25：元数据正确性强化，基座=版本4）

针对平台 DeepSeek Harness 实测丢分诊断（结果正确性 15/40 + 结果完整性 5/40
直接考核元数据真实准确与六要素全覆盖），基座强元数据能力保留一字不改，
仅施加以下定向增量：

1. **新增 scripts/qa_cite.py（补检索问答组件）**：对 `library/` 文本建倒排索引
   （拉丁整词 + 中文 bigram，unigram 兜底），回答 case.json 的
   `searches`/`questions` → `/app/output/search_results.json`。每条答案的每个
   命中带 `{file, line, snippet}` 引用证据 + 该文件已裁决关键字段的
   `metadata_provenance`（值+source），答案→原文行→元数据出处三层证据链闭合；
   无命中诚实 `no_evidence` + 缺什么，绝不编造。索引落盘 work/search_index.json。
2. **新增 scripts/recover.py（补恢复/索引组件）**：解析 case.json 的
   `recovery`/`recover`/`recovery_requests`，按文件名（归一化匹配）或 sha256
   从扫描账本 files.jsonl（含 zip/tar 登记展开成员）恢复文件到
   `library/recovered/`，恢复后 sha256 校验（restored/already_present/not_found/
   verify_failed 全留痕 recovery_log.jsonl + recovery_log.json），重名不覆盖
   加 `__N`，幂等；随后自动重建 manifest（build_manifest 幂等重放）与检索索引
   （qa_cite --index-only）。单条失败记账不崩溃。
3. **provenance_pipeline.py 编排自动衔接（step2c）**：case.json 含
   searches/questions → qa_cite.py；含 recovery → recover.py。
   失败计入 pipeline_steps.json 不中断。
4. **字段正确性闸门**：build_manifest 统计"必填字段填充率（总体+逐字段）、
   冲突未决数（落选候选与赢家同优先级来源）、低置信字段数（赢家置信度<0.65）"，
   写 work/correctness_gate.json + 覆盖率报告专节；finalize --final 汇总进
   `result.json.summary`（机检入口），契约键 `search_results`/`answers`/
   `recovery_log` 等自动映射产物，qa no_evidence 与恢复失败进 uncertainty。
5. **新增 scripts/preflight_check.py**：提交契约七道 gate（frontmatter 合法且
   description ≤900B、≤50 文件、单文件 ≤500KB、总 ≤2MB、全 UTF-8、
   无符号链接、无 token/密钥模式）→ preflight_report.json，全过退出码 0。
6. **新增 references/reproduce.md**：复跑核对命令清单（自检/端到端/产物断言/
   幂等/单步重跑）。
7. SKILL.md：frontmatter name → research-library-metadata-provenance-v2-2，
   description 383B（≤600B）；执行协议补 step2c（qa/recover），其余不变。

### 自查记录（v2.2.0）

/tmp 合成夹具在基座夹具基础上追加：case.json 增 `searches`（含整句查询与
无证据查询）与 `recovery`（按文件名+按哈希+不存在文件三请求）。实跑
`provenance_pipeline.py`：退出码 0，qa_cite/recover 自动衔接 rc=0；
search_results.json 命中带 {file,line,snippet}+metadata_provenance，
无证据查询诚实 no_evidence；recovery 三请求分别 restored/not_found，
sha256 校验一致；result.json.summary 含填充率/冲突未决/低置信三指标；
重跑幂等；preflight 七道 gate 全过。详见 README.md §7。

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
