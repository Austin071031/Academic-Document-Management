# v2.3.0 · 检索问答与索引恢复（基座：版本5 长期归档交付包，archive-first）

核心思想：**交付物是一个可交接、可迁移、可独立校验的归档包**——
一切设计围绕"半年后还能被找到、被信任、被交接"。v2.3.0 在基座上
做定向增量：**检索问答证据化** 与 **真实恢复/索引操作**（对应案例
searches/questions 与 recovery/index 考点）。

## v2.3.0 新增

- `scripts/recovery_ops.py`：按 文件名/别名/sha256 前缀 从归档包、
  账本 inventory.jsonl、压缩包登记、input 原始树逐级恢复文件到
  library/（恢复后逐字节校验，冲突 __dupN 不覆盖）；索引重建
  （FTS5 bigram，无 FTS5 退化 LIKE 并登记 degraded）；全量写
  recovery_log.jsonl。CLI：`--rebuild-index` / `--restore "目标"`。
- `scripts/answer_questions.py`：读取 case.json 的
  searches/questions/queries（字符串与对象两种形态兼容），输出
  search_results.json：每条 {question, answer,
  hits:[{path,line,snippet}], evidence_complete, no_evidence_reason}；
  query_log.jsonl 记录查询语句/耗时/命中数。**无命中绝不编答案**；
  自然语言问题自动剥疑问词尾并收缩重查（query_used 记录实际查询）。
- `scripts/preflight_check.py`：提交契约自检 → preflight_report.json。
- `references/reproduce.md`：复跑核对命令清单。
- pipeline 编排末尾自动衔接 recovery_ops + answer_questions（幂等，
  失败记账不崩溃），结果并入 result.json 的
  sources/summary/change_records。

## 快速开始

```bash
python3 scripts/archive_pipeline.py --input /input --work /app/work --output /app/output
```

仅依赖 Python 3 标准库（sqlite3/zipfile/tarfile/hashlib/difflib）。
全部确定性工作在脚本内完成。

## 交接 SOP（可复用资产）

### 1. 接收归档四件套

从 `/app/output/archive/` 取得：

| 文件 | 作用 |
|---|---|
| `<case_id>_archive.tar.gz` | 资料库全量归档（library/ 树） |
| `SHA256SUMS` | 逐文件 sha256 清单（相对 library 根，两空格分隔） |
| `MANIFEST.json` | 归档清单：每文件路径/大小/sha256/来源/权限/保存期限/密级 |
| `HANDOFF_README.md` | 人类可读交接说明 |

### 2. 校验（两种方法任选）

```bash
# 方法 A：coreutils 直接校验（在 archive/ 目录内解包后）
tar -xzf <case_id>_archive.tar.gz -C restore
cd restore && sha256sum -c ../SHA256SUMS

# 方法 B：独立复跑核对（推荐，含路径穿越防护与统计）
python3 scripts/verify_archive.py --input /input --output /app/output
# 读 verify_report.json：status=ok 且 match==file_count 即全 match
```

### 3. 恢复

```bash
mkdir -p restore && tar -xzf <case_id>_archive.tar.gz -C restore
# restore/ 即 library/ 树；检索库 restore/index/library_index.db 可直接查询：
python3 scripts/query_index.py --db restore/index/library_index.db --q "关键词"
```

### 4. 保存期限与权限

`MANIFEST.json` 的 `retention`/`access_level` 字段给出保存期限与
密级；若值为 `unspecified`，表示原始 case.json/task.md 未声明，
接收方须按制度补录（evidence 字段说明判定依据，绝不编造）。

## 检索

- 建库：`python3 scripts/build_index.py --output /app/output`
  （files 表 + FTS5 虚表 docs；中文按字二元组切词，无 FTS5 自动退化
  LIKE 并在 meta 表登记 degraded=true）
- 查询：`python3 scripts/query_index.py --db .../library_index.db --q "中文关键词"`
  输出命中文件 + 行号 + 命中行文本。

## 诚实性设计

- result.json 必含 `status/sources/uncertainty/change_records`；
- output_contract 逐字段回应，无法满足标 `not satisfied` 并给原因；
- 单文件失败不崩溃：不可读登记 readable=false+原因，计"跳过"不静默；
- 空目录、坏压缩包、不支持格式、路径穿越尝试全部登记；
- verify 结论独立生成，finalize 只回填不粉饰。

## 自查方法

在 `/tmp` 自建合成案例（中文名、改名副本、两版本 txt、含空格中文
CSV 管理备注、好 zip+截断坏 zip、空目录、4 层深目录、含中文可检索
内容；case.json 含 output_contract + searches（字符串与对象各一条）
+ 一条 recovery 任务 + aliases 别名表），真实运行：

```bash
bash selftest/make_case.sh /tmp/case_demo   # 基座合成案例
# v2.3.0 增量项在 case.json 追加：searches 对象形态、aliases、recovery
export PYTHONDONTWRITEBYTECODE=1            # 避免 __pycache__ 落入提交目录
python3 scripts/archive_pipeline.py \
    --input /tmp/case_demo/input \
    --work /tmp/case_demo/work \
    --output /tmp/case_demo/output
python3 scripts/verify_archive.py \
    --input /tmp/case_demo/input --output /tmp/case_demo/output
python3 scripts/query_index.py \
    --db /tmp/case_demo/output/library/index/library_index.db --q "中微子"
python3 scripts/recovery_ops.py \
    --input /tmp/case_demo/input --output /tmp/case_demo/output \
    --restore "<sha256 前缀>" --rebuild-index
python3 scripts/answer_questions.py \
    --input /tmp/case_demo/input --output /tmp/case_demo/output
python3 scripts/preflight_check.py
```

通过标准（v2.3.0 于 2026-11-25 在 /tmp/case_v230 实跑通过，关键
证据如下）：

1. pipeline 两次运行退出码均 0，日志无 traceback，幂等（重跑不产生
   __dup，verify 仍全 match）；
2. `verify_report.json` status=ok，match == MANIFEST.json file_count
   （9/9，二跑含恢复文件后 12/12），mismatch/missing/extra 全 0；
3. `query_index.py --q "液闪"` 命中 4 层深目录中文文件并给出
   文件+行号（line=2）；
4. QA 链路：3 条问题（字符串"中微子"、对象形态"探测器噪声降低了
   多少"、对象形态"保存期限是多久"）全部 evidence_complete=true；
   对象形态问题经剥疑问词尾+收缩重查命中 v2 第 4 行
   "探测器噪声降低 12%"（query_used 已记录）；管理性问题引用
   task.md 来源作答"10年"；query_log.jsonl 每条含 查询/耗时(ms)/
   命中数；
5. recovery：case.json 两条任务（别名"王工终版"→实验记录_v2.txt、
   深层笔记.md）均 result=ok、verified=true、sha256_expected ==
   sha256_actual；独立 CLI `--restore <sha256 前缀>` 命中账本并以来源
   真实文件名恢复；`--rebuild-index` 重建后 index_mode=fts5_bigram、
   degraded=false；篡改已有恢复文件再恢复 → __dupN 改名不覆盖且与
   原件逐字节一致；不存在目标 → 记账 failed（target_not_found），
   不崩溃；
6. result.json status=complete，sources 尾部含
   recovery_ops.py/answer_questions.py，summary.recovery 与
   summary.qa 统计正确，change_records 含 recovery_ops/
   answer_questions 步骤；
7. `duplicates.json` 识别 .bak 改名副本；`versions.json` 给出两版本
   superseded_by 与 diff 摘要；`extracted.json` 记录坏 zip 失败原因；
8. preflight_report.json pass=true（27 文件、136KB、description
   235B、全 UTF-8、无符号链接、无二进制）。

基座合成案例构造脚本见 `selftest/make_case.sh`（UTF-8 中文文件名、
`.bak` 改名副本、`实验记录_v1.txt`/`实验记录_v2.txt` 两版本、
管理备注 CSV、截断的坏 zip、`深/层/目/录/` 四级目录、空目录）；
v2.3.0 的 searches 对象形态/aliases/recovery 任务按上文追加入
case.json 即可复现。

## 目录结构

```
SKILL.md / README.md / CHANGELOG.md / SUBMISSION.md / GITHUB_URL.txt
scripts/  archive_pipeline.py  organize.py  build_index.py
          query_index.py  make_archive.py  verify_archive.py  finalize.py  lib.py
          recovery_ops.py  answer_questions.py  preflight_check.py   # v2.3.0
references/  output_contract.md  edge_cases.md  archive_spec.md
             reproduce.md                                            # v2.3.0
schemas/     result.schema.json  manifest.schema.json
examples/    minimal_example.md
selftest/    make_case.sh
preflight_report.json   # preflight_check.py 自检产物
```

## 预算友好性

- 全流程 0 次模型请求即可跑完（纯脚本），64 次/900s 预算全部留给
  Agent 的异常研判与对 case 特定指令的响应；
- 哈希流式 1 MiB 分块，文本读取限幅 2 MiB/8 MiB，大文件不撑爆内存；
- 索引 content 以 bigram 空格连接存储，避免超长 token 序列。
