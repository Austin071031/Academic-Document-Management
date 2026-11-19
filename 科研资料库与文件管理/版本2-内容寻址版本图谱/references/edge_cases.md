# 边界情况处理清单

| 情况 | 处理 | 证据位置 |
|---|---|---|
| 中文/特殊字符文件名 | 全程 NFC 规范化 + UTF-8；JSON 输出 `ensure_ascii=False` | 所有产物 |
| 内容相同、名字不同的副本 | sha256 相同 → 对象只存一份；duplicate_group 列出全部路径 | versions.json |
| 同一文档多个历史版本 | 相似度聚类成簇，mtime 排序建 supersedes 链，附行增删 | versions.json/.dot |
| 无权限/不可读文件 | 捕获 PermissionError/OSError，`readable=false + reason`，计"跳过"而非"完成"，不静默吞掉 | objects.jsonl、index.skipped、result.uncertainty |
| 坏 zip/tar | 记账 broken + 原因；原包字节仍作为对象入库保留 | index.broken_archives |
| zip 中文成员名乱码 | cp437→UTF-8 还原（老式 zip 未置 UTF-8 标志） | cas_ingest.fix_zip_name |
| 压缩包目录穿越 | 成员名去绝对路径与 `..` 段；嵌套压缩包限深 2 层 | cas_ingest.safe_member_name |
| 空目录 | 登记 `type=dir, empty=true` | objects.jsonl、index.empty_dirs |
| 深层目录 | os.walk 全递归；逻辑树深度不限 | index.json |
| 符号链接 | 不跟随（followlinks=False），登记 skipped+原因 | objects.jsonl |
| 超大文件 | sha256 流式 1 MiB 分块；文本分析截断 256 KB（谱系）/512 KB（检索） | cas_common |
| 二进制文件 | 内容嗅探（NUL 字节/UTF-8 解码）判定非文本：入库归类照常，不进版本簇与检索 | index.is_text |
| tree 重名冲突 | 追加 `__dupN`（N 从 1 递增），绝不覆盖已有文件 | index.stats.tree_conflicts_renamed |
| mtime 缺失 | 版本链排序排尾；不伪造时间 | lineage |
| case.json 缺失 | step0 记 warning，按空契约做通用整理，result.json 照出 | run_log.json |
| 契约字段无法映射 | 置 null + uncertainty 说明，绝不编造 | result.uncertainty |
| 单文件/单成员失败 | 捕获、记账、继续；绝不因单点失败拖垮全链路 | 各账本 errors |
| 单步骤崩溃 | run_step 捕获异常记 run_log，继续后续步骤；result.json 至少 partial | work/run_log.json |
| tree 被误改 | 对象库只读 + tree 复制隔离；verify_cas.py 重哈希必现形（退出码 1） | verify_report.json |

## 六要素覆盖核对

1. **文件类型**：扩展名分类映射（论文文档/表格数据/数据文件/代码脚本/笔记文本/图片图形/压缩包/其他）+ 内容嗅探。
2. **元数据字段**：`{field, value, source, evidence}` 五元组，filename 模式优先，CSV/md join 补充，抽不到 null+原因。
3. **目录层级**：逻辑树 `项目/年份/类型/规范文件名`；源目录结构保留在 source_path。
4. **重复文件**：sha256 精确分组（按内容不按名字）。
5. **版本差异**：difflib 相似度聚类 + supersedes 边 + 行增删 diff_summary。
6. **权限与来源**：每项记录 permissions（八进制）、origin（direct / archive:<包路径>）、readable/skipped+原因。
