# 科研资料库与文件管理 Skill · v2.1.0（内容寻址版本图谱 + 可核验证据强化）

## 一句话

借鉴 git 对象库思想：把混乱科研资料库以 **sha256 内容寻址**入库（天然去重），
checkout 出规范目录工作树，再用**内容相似度 + mtime** 建版本谱系 DAG，
附倒排索引检索与第三方可复跑的核对器，最终产出诚实的 `result.json`。
v2.1.0 增量：谱系/目录树渲染成**真实 SVG/PNG 证据图**（纯标准库手写 SVG 必出，
matplotlib 仅 optional）、按 sha256 前缀/文件名**从对象库恢复并哈希校验**、
索引重建与检索结果顶层同步、提交契约自检。

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

# v2.1.0 新增单步（也已编入 cas_run.py 全链路）
python3 scripts/render_evidence.py --input /input --work /app/work --output /app/output  # SVG/PNG 证据图
python3 scripts/recover.py         --input /input --work /app/work --output /app/output  # 恢复+索引重建+检索同步
python3 scripts/preflight_check.py --report /app/output/preflight_report.json            # 提交契约自检
```

仅依赖 Python 3 标准库（测试环境 Python 3.12.4）；matplotlib 只作 optional
导入用于 PNG 预览，缺失时自动降级 SVG only 并登记，绝不报错。对 `/input`
只读，全部产物写 `/app/output`，中间产物写 `/app/work`。
复跑核对的确切命令见 `references/reproduce.md`。

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

### v2.1.0 增量自查（2026-11-25，/tmp/casetest21）

夹具：中文名文件、内容相同改名副本、共享 3 行的两版本 txt（ratio=0.50）、
CSV 管理备注、md 版本备注、好 zip（中文成员名）、坏 zip、空目录、五层深目录；
`case.json` 含 6 个契约字段（含 1 个不存在字段）、2 条 searches、1 条 question、
**3 条 recovery 请求**（按文件名、按 sha256 前缀、无匹配负例各 1）。

`cas_run.py` 真实运行 **exit=0，十二步全 ok**（ingest→…→verify→render_evidence
→recover_qa→verify_after_recover→preflight→merge_evidence），逐项断言 17/17 PASS：

- **证据图**：`evidence/lineage.svg` 为良构 UTF-8 XML（ElementTree 解析通过），
  含 **1 条真实 supersedes 箭头边**（sim=0.5，+4/-2 行）与中文节点名；
  `tree_overview.svg` 含树形缩进与中文路径；本环境有 matplotlib，
  `lineage.png` 成功渲染（缺 CJK 字体时字形告警已静默，PNG 仅作预览，
  SVG 为权威可编辑图源）。
- **降级路径**：用 `sys.modules["matplotlib"]=None` 模拟无 matplotlib 环境重跑
  render_evidence——SVG 照常产出、PNG 跳过、warnings 恰为
  `["matplotlib unavailable, SVG only"]`、不崩溃（该 warning 经 cas_run 并入
  result.json 的 uncertainty）。
- **恢复**：`recovery_log.jsonl` 5 条记录：文件名恢复 ok、sha256 前缀恢复 ok
  （均 `hash_verified=true`，落盘 `tree/recovered/`）、无匹配请求 failed+原因、
  rebuild_index ok、search_sync ok；恢复后 verify_after_recover 仍 0 mismatch
  （恢复文件已登记进 index.json）。
- **检索**：顶层 `search_results.json` 两条查询均有命中（9 次/14 次），
  命中带 path+line+snippet。
- **收口**：result.json 含 case_id + 6 个契约字段全量（不存在字段=null+uncertainty），
  status=complete_with_warnings（坏 zip 诚实降级）；artifacts 新增
  evidence_lineage_svg/png、recovery_log、search_results_top、preflight_report。
- **preflight**：对 Skill 包自身 6 项检查全过（25 文件、136 KB、全 UTF-8、
  无符号链接、frontmatter description 267B）；负例测试（含符号链接目录）
  正确报 FAILED 且退出码 1。
- 自查中修复的问题：render_lineage_svg 宽度计算绕圈（简化为按节点最大 x+w）、
  matplotlib 缺字形告警刷 stderr（已 catch_warnings 静默）。

### v2.0.0 基座自查（2026-11-19）

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
