# 方法学：内容寻址对象库 + 版本谱系图谱

## 1. 为什么是内容寻址（CAS）

git 的核心洞察：**用内容哈希作为对象的唯一身份**，身份与名字、位置、时间解耦。
对混乱科研资料库而言这直接解决三个痛点：

- **重复/别名**：改名备份副本内容相同 → sha256 相同 → 对象只存一份，
  账本中自然呈现"多个路径 → 一个 content_id"，这就是精确重复组，零误报。
- **完整性**：任何产物（tree、报告）里的文件都能用哈希回溯到对象库中的唯一字节序列；
  对象入库后置只读（0o444），tree 用**复制**而非硬链接 checkout，避免共享 inode 被误写污染。
- **可核对**：第三方无需信任运行方，重新哈希即可验证（见 §5）。

对象布局 `objects/<sha前2位>/<sha256>` 与 git 相同：前 2 位分桶避免单目录文件过多。

## 2. 精确去重 vs 相似版本

两级判定，都**按内容不按文件名**：

| 层级 | 判定 | 结果 |
|---|---|---|
| 精确 | sha256 相等 | duplicate_group（别名/副本） |
| 相似 | difflib 行级 ratio ≥ 0.40 且 < 1.0 | 同一版本簇 |

相似度用 `difflib.SequenceMatcher`（纯 stdlib）作用于**行序列**而非字符序列：
行级匹配对文档版本演化（增删段落）更稳健，且先 `quick_ratio()` 剪枝避免全量 O(n²·L)。

## 3. 版本谱系 DAG

- **节点**：一个 content_id 一个节点（别名并入 `all_paths`），携带 mtime/size/path。
- **簇内排序**：按 mtime 升序；mtime 缺失排尾（不确定，如实记录）。
- **边**：相邻版本 (旧→新) 生成 `supersedes` 边：from=新节点 → to=旧节点，
  附 `inverse=superseded_by`、`similarity`、`diff_summary{lines_added, lines_removed}`
  （由 unified diff 计数，排除 +++/--- 头）。
- 结果是 DAG（链是特例）：同一旧版本可分叉出多个新版本，不同簇之间无边。
- `versions.dot` 输出 Graphviz 文本，`dot -Tpng versions.dot` 即可渲染。

## 4. 元数据出处（provenance）

每个元数据字段是 `{field, value, source, evidence}`：

- `filename`：文件名模式 `项目号_作者_年份_类型.ext`（优先级最高，evidence 为原文件名）；
- `companion_table`：伴随 CSV（含"文件名/名称/path"列）按文件名 join，evidence 为 `表名: 原始行`；
- `admin_note`：管理性备注 md/txt 中出现该文件名的行，evidence 为 `文件名: 行内容`；
- `agent_inference`：代理推断（本流水线不主动产生）；
- 抽不到：`value=null, source=null, evidence=原因`。**绝不猜。**

## 5. 第三方如何复跑核对

1. 重跑 `python3 scripts/verify_cas.py --input /input --work /app/work --output /app/output`：
   重新哈希 `library/tree/` 每个文件，检查 (a) 与 index.json 登记的 content_id 一致，
   (b) 对象 `objects/<前2位>/<sha256>` 存在，(c) 对象库盘点无丢失。退出码 0/1。
2. 手动抽查：`sha256sum` 任一 tree 文件 → 在 `objects.jsonl` 中 grep 该哈希 →
   应看到全部源路径（别名）与 origin。
3. 版本边抽查：`versions.json` 中任取一条 supersedes 边，按 from/to 的 content_id
   在对象库取出两个对象做 `diff`，行增删数应与 `diff_summary` 一致。
4. 检索抽查：`search_results.json` 任一命中，打开对应 tree 文件的对应行号核对片段。

## 6. 复杂度与预算

- 哈希/入库：O(总字节数)，流式 1 MiB 分块，内存恒定。
- 相似度：O(t²) 对文本内容（t=唯一文本对象数），quick_ratio 剪枝；
  单文本截断 256 KB。评测规模下秒级完成。
- 检索：建索引 O(文本总量)，查询 O(命中数)。
- 全部确定性工作离线完成，模型请求只用于最终解读，不消耗在搬运上。
