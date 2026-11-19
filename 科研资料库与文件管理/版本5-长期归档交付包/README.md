# 版本5 · 长期归档交付包（archive-first）

核心思想：**交付物是一个可交接、可迁移、可独立校验的归档包**——
一切设计围绕"半年后还能被找到、被信任、被交接"。

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

在 `/tmp` 自建合成案例（中文名、改名副本、两版本 txt、CSV 管理备注、
坏 zip、空目录、深目录、含中文可检索内容），真实运行：

```bash
bash selftest/make_case.sh /tmp/case_demo          # 造合成 /tmp/case_demo/input
python3 scripts/archive_pipeline.py \
    --input /tmp/case_demo/input \
    --work /tmp/case_demo/work \
    --output /tmp/case_demo/output
python3 scripts/verify_archive.py \
    --input /tmp/case_demo/input --output /tmp/case_demo/output
python3 scripts/query_index.py \
    --db /tmp/case_demo/output/library/index/library_index.db --q "中微子"
```

通过标准（本仓库已实跑通过）：

1. pipeline 退出码 0，日志无 traceback；
2. `verify_report.json` 的 `status=ok` 且
   `match == MANIFEST.json file_count`（归档解包逐文件全 match）；
3. `query_index.py --q "中微子"` 命中合成中文文件并给出 文件+行号；
4. `duplicates.json` 识别改名副本；`versions.json` 给出两版本
   superseded_by 与 diff 摘要；
5. `extracted.json` 记录坏 zip 失败原因，不崩溃；
6. `result.json` status=complete，uncertainty 仅含"unspecified 待补录"
   类诚实条目。

合成案例构造脚本见 `selftest/make_case.sh`（UTF-8 中文文件名、
`.bak` 改名副本、`实验记录_v1.txt`/`实验记录_v2.txt` 两版本、
管理备注 CSV、截断的坏 zip、`深/层/目/录/` 四级目录、空目录）。

## 目录结构

```
SKILL.md / README.md / CHANGELOG.md
scripts/  archive_pipeline.py  organize.py  build_index.py
          query_index.py  make_archive.py  verify_archive.py  finalize.py  lib.py
references/  output_contract.md  edge_cases.md  archive_spec.md
schemas/     result.schema.json  manifest.schema.json
examples/    minimal_example.md
selftest/    make_case.sh
```

## 预算友好性

- 全流程 0 次模型请求即可跑完（纯脚本），64 次/900s 预算全部留给
  Agent 的异常研判与对 case 特定指令的响应；
- 哈希流式 1 MiB 分块，文本读取限幅 2 MiB/8 MiB，大文件不撑爆内存；
- 索引 content 以 bigram 空格连接存储，避免超长 token 序列。
