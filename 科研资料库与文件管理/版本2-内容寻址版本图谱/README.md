# 科研资料库与文件管理 Skill · 版本2（内容寻址版本图谱）

## 一句话

借鉴 git 对象库思想：把混乱科研资料库以 **sha256 内容寻址**入库（天然去重），
checkout 出规范目录工作树，再用**内容相似度 + mtime** 建版本谱系 DAG，
附倒排索引检索与第三方可复跑的核对器，最终产出诚实的 `result.json`。

## 使用方法

```bash
# 全链路（推荐）
python3 scripts/cas_run.py --input /input --work /app/work --output /app/output

# 或单步执行（每个脚本都可独立运行）
python3 scripts/cas_ingest.py  --input /input --work /app/work --output /app/output
python3 scripts/finalize.py    --input /input --work /app/work --output /app/output --stage partial
python3 scripts/build_index.py --input /input --work /app/work --output /app/output
python3 scripts/lineage.py     --input /input --work /app/work --output /app/output
python3 scripts/search.py      --input /input --work /app/work --output /app/output
python3 scripts/finalize.py    --input /input --work /app/work --output /app/output --stage final
python3 scripts/verify_cas.py  --input /input --work /app/work --output /app/output  # 复跑核对
```

仅依赖 Python 3 标准库（测试环境 Python 3.12.4）。对 `/input` 只读，全部产物写 `/app/output`，中间产物写 `/app/work`。

## 方法

1. **内容寻址对象库**（cas_ingest）：流式 sha256（1 MiB 分块）→
   `library/objects/<sha前2位>/<sha256>`。对象只存一份：内容相同的改名副本在对象层自动去重，
   账本 `objects.jsonl` 记录每个源路径 → 哈希的映射（含 size/mtime/权限/origin）。
   zip/tar 用 stdlib 展开：成员名安全化（防 `..` 目录穿越）、cp437→UTF-8 乱码名还原、
   嵌套压缩包限深 2 层；坏包记账但保留原包字节。
2. **逻辑索引与工作树**（build_index）：文件名模式 `项目号_作者_年份_类型.ext` 解析优先；
   每个元数据字段都是 `{field, value, source, evidence}` 五元组
   （source ∈ filename|content|companion_table|admin_note|agent_inference），
   抽不到则为 `value=null + 原因`，**绝不猜**。伴随 CSV（含"文件名/名称/path"列的表）
   与管理性备注 md/txt（文件名含 备注/说明/版本/管理/note 等）按文件名 join 为 notes。
   工作树按 `项目/年份/类型/规范文件名` 组织，**复制**（非硬链接）出树以保护对象库；
   重名冲突追加 `__dupN`，绝不覆盖。
3. **版本谱系**（lineage）：三层判定，全部按内容不按文件名——
   (a) sha256 分组 = 精确重复（别名/副本）；
   (b) 文本文件两两 difflib 行级相似度（quick_ratio 剪枝，阈值 0.40）并查集聚类 = 版本簇；
   (c) 簇内按 mtime 排序建链，相邻版本生成
   `supersedes` 边（from=新→to=旧，附 similarity 与 diff_summary 行增删数）。
   同时输出 Graphviz `versions.dot` 供可视化核对。
4. **检索**（search）：倒排索引 term→[(path, 行号)]，term = 拉丁词(小写) + CJK 单字 + CJK 二元组；
   查询先取 posting 候选行再按 精确子串/词元覆盖 排序；命中带 文件+行号+片段。
   questions 以 top-5 证据片段作答（如实说明需代理归纳）。
5. **诚实收口**（finalize + verify）：result.json 含 case_id + output_contract **全部字段**；
   无法映射的字段置 null 并写 uncertainty；sources 带 sha256 前缀可追溯；
   change_records 记录本次运行全部动作；verify_cas.py 重哈希 tree/ 与对象库逐项比对。

## 限制

- 不解析 PDF/Word/图片等二进制内部语义（仅哈希 + 文本嗅探）。
- difflib 两两比较 O(n²)，适配评测规模语料；相似度阈值 0.40 可能漏掉改动极大的版本。
- 非文本文件（如 .bin）不进版本簇与检索索引，但入库、登记、归类照常。
- mtime 缺失的版本节点排在链尾并在 uncertainty 中体现（如发生）。
- 以 root 运行时 chmod 0o444 的对象只读保护可被绕过，verify_cas.py 是最终防线。

## 自查方法（合成案例真实运行，全部通过）

在 `/tmp/casetest` 自建合成案例：中文名文件、内容相同的改名副本、同一文档两个版本 txt、
CSV 版本备注、md 管理备注、好 zip（含中文名成员）、坏 zip、空目录、五层深目录、二进制 .bin，
`case.json` 含 6 个契约字段（含 1 个不存在的字段）、2 条 searches、1 条 question。

运行 `cas_run.py` 的关键证据（exit=0，七步全 ok，总耗时 <1s）：

- **入库**：`files_seen=11, objects_stored=11, dedup_hits=1`（改名副本命中去重）、
  `empty_dirs=1`（空目录已登记）、`broken_archives=1`（坏 zip 记账：BadZipFile），
  对象库落盘 11 个对象且无重复哈希；zip 中文成员名正确还原为 `资料包.zip::补充数据.txt`。
- **索引**：`indexed_files=10, unique_contents=9`；`项目A_张三_2023_论文.txt` →
  逻辑路径 `项目A/2023/笔记文本/…`，year 字段 provenance 为 `source=filename`；
  CSV 与 md 备注成功 join（每文件 2 条 notes）；同名文件冲突生成 `__dup1`（另测）。
- **谱系**：`duplicate_groups=1`（`项目A_张三_2023_论文.txt = 项目A数据/副本-最终版(张三).txt`），
  `version_clusters=1, supersedes_edges=1`（v2 supersedes v1，sim=0.4444，+3/-2 行），
  `versions.dot` 输出合法 digraph。
- **检索**：`关键词Alpha` 命中 3 处、`实验数据` 命中 5 处（均带 文件+行号+片段），
  question 返回 5 条证据片段。
- **收口**：`result.json` 含全部契约字段（不存在字段=null + uncertainty），
  status=`complete_with_warnings`（因坏 zip 诚实降级），
  `verify_report.json` ok=true；篡改 tree 文件后 verify 退出码 1 并报 2 处 mismatch（另测）。
