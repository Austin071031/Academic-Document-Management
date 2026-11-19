# 科研资料库元数据溯源台账（版本4）—— 完整说明

版本4的核心主张：**元数据不是"抽出来的值"，而是"带出处、证据、置信度的台账记录"**。
每个字段从候选产生到最终入册，全程留痕；冲突有明确的、写在产物里的裁决规则；
抽不到就是 `null` + 原因，绝不猜测。这是可复用资产：换一批资料库，只需改
`config/field_dictionary.json`（字段、别名、正则），脚本零改动。

## 1. 架构总览

```
/input ──► scan（流式sha256/无权限登记/空目录登记/zip·tar展开登记）
             │ files.jsonl + scan_summary.json
             ▼
   extract_from_filename ─┐
   extract_from_content ──┼─► candidates.jsonl（逐字段候选：value+source+evidence+confidence）
   join_companion ────────┤
   parse_admin_notes ─────┴─► facts.jsonl（superseded_by / alias 事实）
             │
             ▼ adjudicate.py（优先级裁决，冲突留痕）
        provenance.jsonl（逐字段台账记录）
             │
             ▼ build_manifest.py（sha256重复组 / 版本链+差异摘要 / library组织）
   manifest.json · manifest.csv · duplicates.json · versions.json · field_coverage_report.md
             │
             ▼ finalize.py（--partial 先行，--final 汇总）
        /app/output/result.json
```

8 个功能脚本 + 1 个编排器 + 1 个共享工具层，均可独立运行、可重入（adjudicate 覆盖重写，
Agent 补录 agent_candidates.jsonl 后重跑 adjudicate+build_manifest 即可合并）。

## 2. 字段字典设计（config/field_dictionary.json）

字典是管线的"宪法"，分五部分：

- **fields**：每个字段含 `definition`（定义）、`legal_sources`（合法来源白名单）、
  `format`（正则或格式说明）、`required`（是否必填）、`example`（示例）。
  管线只产出/裁决字典登记的字段；评测题目指定的必需字段在 step1 合并进 `required`。
- **field_aliases**：表头/键名别名映射（如 `标题/题名/title` → `title`），
  供伴随表 join 与"字段: 值"行解析使用。
- **filename_patterns**：可配置文件名正则集。每条含命名分组→字段映射，例如
  `^(.+?)_(.+?)_(\d{4})_(.+)\.([a-z0-9]+)$` → project/authors/year/doc_type。
- **content_sniffers**：内容嗅探正则集（DOI、日期、项目号、仪器型号、版本号、关键词……）。
- **source_priority / source_confidence**：与 `scripts/ledger_common.py` 常量一致，
  是裁决规则与置信度口径的单一事实来源。

## 3. 裁决规则（adjudicate.py）

同一 `(文件, 字段)` 的多来源候选按优先级取值：

```
admin_note  >  companion_table  >  content  >  filename  >  agent_inference
 0.95            0.85               0.75        0.60           0.50
```

- 同级多值：取置信度高者；再平按证据字符串字典序取确定性第一个（可复现）。
- **落选候选不丢弃**：全部写入该记录的 `conflicts` 数组（value+source+evidence）。
- 同值多来源：不算冲突，在 `evidence` 里追加 `corroborated by: ...`（多源互证）。
- `admin_note` 中的"字段: 值"行作为库级默认（file=`*`）：仅当某文件该字段无任何
  候选时补用，置信度 ×0.9，证据前缀 `library-wide default applied`。
- 管理备注的 superseded_by 事实还用于版本链裁决，优先于启发式（见 §5）。

## 4. 置信度口径

置信度是**来源可信度**，不是"模型有多确定"：

| source | 基准置信度 | 含义 |
| --- | --- | --- |
| admin_note | 0.95 | 管理人显式记录的事实（备注表/版本说明） |
| companion_table | 0.85 | 伴随元数据表的结构化取值 |
| content | 0.75 | 文件正文嗅探（结构化正则）；启发式标题行下调到 0.65 |
| filename | 0.60 | 文件名模式解析 |
| agent_inference | 0.50 | Agent 推断，必须有可见依据；任何证据来源均可覆盖 |

六要素覆盖：台账记录含 **字段(what)、取值(value)、来源(where/source)、
证据(why/evidence)、置信度(how sure/confidence)、时间戳(when/ts/adjudicated_at)**，
外加冲突清单与裁决规则串，产物自证清白。

## 5. 重复与版本判定

- **重复**：流式 sha256（256KB 块）按内容判定，size>0；同哈希组保留路径最短者为
  主副本，写 `duplicates.json`。改名副本天然命中（内容不变哈希不变）。
- **版本链**：先采信管理备注解析出的 `superseded_by` 事实（人能对上的才算数，
  名称按归一化主干匹配到实际文件）；再用启发式兜底——剥离
  `vN/日期/副本/backup/final/最终版/定稿` 等标记后主干相同但哈希不同者，
  按 mtime 排序成链。`versions.json` 每条含 `superseded_by` + 差异摘要
  （文本：行数与 +/-/~ 行数，基于前 64KB；二进制：大小/mtime 差）+ 依据。

## 6. 工程要点

- Python3 仅标准库；无第三方依赖，无网络。
- 编码：chardet 不可用，按 utf-8-sig → utf-8 → gb18030 → utf-16 依次尝试并**记录实际
  使用编码**到证据串；全失败则 utf-8+replace + 告警。
- PDF：仅当 `shutil.which("pdftotext")` 存在时 subprocess 调用（前 3 页）；
  找不到或空文本层 → 登记 `content_unreadable.jsonl`（source=content, status=unreadable）。
- 压缩包：zipfile/tarfile stdlib 展开，路径穿越（`..`/绝对路径）条目跳过，
  单条目 ≤200MB、单包 ≤2000 条目防解压炸弹；坏包登记不崩溃。
- 中文/特殊字符文件名：全程 UTF-8 + NFC 归一化比较；library 路径组件清洗 `/`、`\\`。
- 单文件失败不崩溃：所有抽取点 try/except 隔离；不可读/无权限登记 `readable=false`
  + 原因并计入 uncertainty；空目录登记。
- 预算友好：确定性工作全在脚本；Agent 只做 step3 的克制成份。

## 7. 自查方法（已在 /tmp 合成案例上真实运行）

构造合成案例 `/tmp/prov4_case/input`：

- 中文文件名 `项目A_张三_2023_实验记录.txt` 及其**内容相同的改名副本**
  `项目A_张三_2023_实验记录_副本.txt`；
- **两个版本**的报告：`报告_最终版.txt` 与 `报告_最终版_v2.txt`（内容不同）；
- CSV 管理备注 `管理/版本备注.csv`，含"原文件,新文件"替代关系行 + 一行文本"已被…替代"；
- 伴随元数据表 `元数据/伴随元数据.csv`（含一行指向不存在文件的"幽灵行"）；
- 坏 zip（文本文件改名 .zip）、空目录、五层深目录下的 csv、GBK 编码 txt；
- `case.json` 含 `required_fields` 与 output_contract 五键。

运行：
```bash
python3 scripts/provenance_pipeline.py --input /tmp/prov4_case/input \
    --work /tmp/prov4_case/work --output /tmp/prov4_case/output
```
验证点（全部通过，详见 CHANGELOG 与 §8）：
1. 管线退出码 0，全部 8 个子步骤 rc=0；
2. `provenance.jsonl` 每条含 field/value/source/evidence/confidence/conflicts/rule；
3. 伴随表覆盖文件名冲突值（如 year），`conflicts` 保留落选证据；
4. 重复组正确识别改名副本；版本链 `报告_最终版.txt → 报告_最终版_v2.txt`
   来自管理备注事实且带文本差异摘要；
5. 坏 zip、空目录、幽灵行进 uncertainty；GBK 文件按 gb18030 解码成功并在证据中注明；
6. `result.json`：case_id 正确、output_contract 五键填产物路径、status=complete。

复现自查：`bash` 重建 /tmp/prov4_case（见 CHANGELOG "自查记录"），重跑上述命令即可。

## 8. 与其他版本的区分

见 CHANGELOG.md "架构区分要点"：字段字典先行、逐字段台账+冲突留痕、
Agent 推断被制度性压到最低优先级且必须留据。
