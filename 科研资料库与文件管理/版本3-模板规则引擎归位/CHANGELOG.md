# CHANGELOG

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
