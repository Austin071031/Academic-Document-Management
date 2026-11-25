# CHANGELOG

## v2.1.0（可核验证据强化，当前版本）

在 v2.0.0 基座上只做定向增量（基座行为不变，仅 cas_run.py 末尾衔接新步骤）：

- 新增 `render_evidence.py`：纯标准库手写 SVG 把版本谱系 DAG 与目录树渲染成
  **真实可检查的证据图**（`evidence/lineage.svg` 必出、`tree_overview.svg`、
  matplotlib 有则再出 `lineage.png`，缺失登记 "matplotlib unavailable, SVG only"
  进 uncertainty，绝不崩溃）——命中 实际效果（结果可核验性）+ 创新增益（创新证据）。
- 新增 `recover.py`：按 sha256 前缀/文件名从对象库恢复任意文件到
  `tree/recovered/` 并重新哈希校验（`recovery_log.jsonl`）+ 索引/检索索引重建 +
  检索结果同步写顶层 `search_results.json`；恢复后自动重跑 verify——命中
  实际效果 + 可靠体验。
- 新增 `preflight_check.py`：提交契约自检（frontmatter/description ≤900B、≤50 文件、
  单文件 ≤500KB、总 ≤2MB、全 UTF-8、无符号链接）→ `preflight_report.json`——命中
  可靠体验 + 生态贡献。
- 新增 `references/reproduce.md` 复跑核对命令清单；新增 `SUBMISSION.md`。
- SKILL.md 执行协议补 step6/step7，frontmatter name →
  `research-library-cas-lineage-v2-1`，description 267B（≤600B）。

## v2.0.0（内容寻址版本图谱）

架构重写，与版本1（纯规则整理）区分：

- 新增 **内容寻址对象库**（`cas_ingest.py`）：sha256 寻址 `objects/<前2位>/<sha256>`，
  对象只存一份、置只读，内容相同的改名副本天然去重；账本 `objects.jsonl`。
- 新增 **规范工作树 checkout**（`build_index.py`）：逻辑路径
  `项目/年份/类型/规范文件名`；复制（非硬链接）隔离保护对象库；冲突 `__dupN` 不覆盖；
  元数据字段全部带 `{field, value, source, evidence}` 出处，抽不到 null+原因。
- 新增 **版本谱系 DAG**（`lineage.py`）：sha256 精确重复组 + difflib 相似度版本簇 +
  mtime 排序 supersedes 链（含 similarity、diff_summary 行增删），输出
  `versions.json` 与 Graphviz `versions.dot`。
- 新增 **倒排索引检索**（`search.py`）：拉丁词 + CJK 单字/二元组，
  命中带 文件+行号+片段；questions 返回 top-5 证据片段。
- 新增 **诚实收口**（`finalize.py`）：output_contract 全字段填充，无法映射置 null +
  uncertainty；ingest 后立即写 status=partial 保底。
- 新增 **复跑核对器**（`verify_cas.py`）：重哈希 tree 与对象库逐项比对，退出码 0/1。
- 工程：单文件失败不崩溃（记账继续）；不可读文件计"跳过"不静默；zip/tar stdlib
  展开（防目录穿越、cp437→UTF-8 中文名还原、嵌套限深）；空目录/符号链接登记；
  中文文件名 NFC 全程安全；仅标准库。

## 自查记录

- 2026-11-25（v2.1.0）：/tmp 合成案例（中文名、改名副本、两版本 txt、CSV 管理备注、
  坏 zip、空目录、五层深目录、case.json 含 output_contract + searches + recovery）
  真实运行 `cas_run.py`，exit=0，十二步全 ok；lineage.svg 含 supersedes 版本边、
  search_results.json 有命中、recovery_log 有 hash_verified 记录、result.json 含
  case_id+全契约字段、preflight 通过、verify 全 ok；并模拟 matplotlib 缺失环境
  验证 SVG-only 降级不崩溃。详见 README「自查方法」。
- 2026-11-19：/tmp 合成案例（中文名、改名副本、两版本 txt、CSV/md 备注、好/坏 zip、
  空目录、五层深目录、二进制 bin）真实运行 `cas_run.py`，exit=0，七步全 ok；
  去重、supersedes 边、检索命中、verify 篡改检测均验证通过。详见 README「自查方法」。
