# CHANGELOG

## v2.4.0（增益证据与生态完备，2026-11-25）

基座：版本3-模板规则引擎归位。定向增量（基座 plan/apply/audit/finalize
行为一字未改；organize.py 仅在编排末尾追加 step6–8 与各 step 计时）。

### 新增
- `scripts/gain_report.py`：可机检增益度量——处理文件数、归位条目数、
  精确去重合并条目数、版本链边数、恢复/检索操作数、脚本总耗时、
  模型调用数=0、幂等复算（同输入同配置重建计划比对条目哈希）；
  "前后对照"小节：整理前混乱度（根目录散落文件/重名组/无出处字段）
  vs 整理后（归位率/字段填充率/可校验文件比例）。所有数字来自
  plan/journal/audit/duplicates/versions/run_timing 真实计数。
- `scripts/qa.py`：倒排索引（CJK 二元组 + 拉丁词）回答 case.json
  searches/questions，命中带 文件+行号+片段，无命中诚实 no_evidence。
- `scripts/recover.py`：按文件名/sha256 从账本（plan.json）与压缩包
  登记恢复并校验，写 recovery_log.jsonl（recovered/not_found/error）。
- `scripts/preflight_check.py`：提交契约自检（frontmatter 合法且
  description ≤900B、≤50 文件、单文件 ≤500KB、总 ≤2MB、全 UTF-8、
  无符号链接、无密钥模式）→ preflight_report.json，退出码即结论。
- `docs/USAGE.md`：完整调用步骤/输入输出/限制/失败处理/自查方法。
- `docs/REUSE.md`：目录模板、字段字典、规则配置、脚本独立复用指南。
- `references/reproduce.md`：复跑核对命令清单。
- `SUBMISSION.md`（Attempt/得分待回填）；GITHUB_URL.txt 指向 v2.4.0 目录。

### 修改
- `SKILL.md`：frontmatter name → research-library-rule-engine-v2-4；
  description 精简；执行协议补 step6 qa / step7 recover / step8 gain_report；
  输出清单补新工件；其余不变。
- `scripts/organize.py`：仅追加 step6–8 编排（均 tolerate_failure）与
  run_timing.json 计时，step0–5 未动。

### 自查（合成夹具实跑）
- 见 README「自查方法」v2.4.0 节：夹具含中文名、改名副本、两版本 txt、
  CSV 管理备注、坏 zip、空目录、5 层深目录、case.json 含
  output_contract+searches+recovery。入口实跑两次：退出码 0、
  gain_metrics 数字与夹具构造一致、幂等哈希一致、search_results 有命中、
  recovery 带校验、audit 全 match、preflight 全 pass。

## v3.0.0（版本3：声明式模板 + 规则引擎归位）

### 架构
- 目录规范即配置：`config/layout_template.json` 统一定义模板、字段字典、
  路由规则（priority + 第一条匹配生效 + DEFAULT 兜底）与命名规范化策略。
- 六步执行协议 organize.py：step0 检查+partial result → step1 题目约定
  翻译进配置 → step2 plan dry-run → step3 apply → step4 audit → step5 finalize。
- plan/apply 分离：先出可审阅计划再落地；journal.jsonl 全程带 reverse，
  可回滚；audit 重哈希核对 + 规则覆盖率报告。

### 功能
- 流式 sha256；zip/tar stdlib 展开登记；空目录 quarantine；不可读
  文件/目录显式登记（含 os.walk onerror，杜绝静默跳过）。
- 三路元数据解析（文件名模式/伴随 CSV/管理备注 md）带出处合并，
  冲突时 CSV > md > 文件名模式。
- 重复（内容哈希）与版本链（基础名 + 不同哈希 + superseded_by）识别。
- 命名规范化：NFKC、非法字符替换、空白折叠、长度截断、Windows 保留名
  防护、冲突 `__dupN` 绝不覆盖。
- result.json：case_id + output_contract（三种形态兼容）+ 诚实
  status/sources/uncertainty/change_records；partial 先行、原子写。

### 自查（合成案例）
- 11 文件合成库（中文名、改名副本、双版本、CSV 备注、坏 zip、好 zip、
  空目录、深目录、特殊字符名）：零报错，plan 11/11 与 apply/audit 一致，
  audit all_match=True，覆盖率 R01:2/R03:1/R04:2/R06:6=11。
- 约定翻译 `{topic}/{year}/{kind}/{name}` 正确生效（同义字段镜像）。
- 冲突规范化名归位 `__dup2`；无权限文件/目录（nobody 运行）登记
  readable=false，不静默。
