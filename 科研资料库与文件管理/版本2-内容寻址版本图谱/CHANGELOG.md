# CHANGELOG

## v2.0.0（内容寻址版本图谱，当前版本）

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

- 2026-11-19：/tmp 合成案例（中文名、改名副本、两版本 txt、CSV/md 备注、好/坏 zip、
  空目录、五层深目录、二进制 bin）真实运行 `cas_run.py`，exit=0，七步全 ok；
  去重、supersedes 边、检索命中、verify 篡改检测均验证通过。详见 README「自查方法」。
